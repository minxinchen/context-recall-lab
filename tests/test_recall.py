import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import recall

ROOT = Path(__file__).resolve().parents[1]


class RecallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        shutil.copytree(ROOT/'examples', self.base/'examples')
        self.manifest = self.base/'examples/manifest.json'
        self.db = self.base/'index.sqlite'
        recall.build(self.manifest, self.db)

    def packet(self):
        return recall.search(self.db, '部署 凍結 預算')

    def test_chinese_retrieval_and_exact_citations(self):
        p = self.packet()
        self.assertEqual(p['hits'][0]['id'], 'session-a-raw')
        self.assertTrue(recall.verify(self.db, p)['valid'])
        self.assertFalse(p['answer_generated'])

    def test_english_retrieval(self):
        self.assertEqual(recall.search(self.db, 'API timeout')['hits'][0]['id'], 'session-b-raw')

    def test_absent_query_no_answer(self):
        p = recall.search(self.db, 'volcano_xyz')
        self.assertEqual(p['status'], 'no_match')
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_unresolved_is_preserved(self):
        p = recall.search(self.db, '部署', kinds=['structured'])
        h = p['hits'][0]
        self.assertEqual(h['review'], 'unresolved')
        self.assertEqual(h['raw_parent']['id'], 'session-a-raw')
        # Verbatim citation verification does NOT certify the statement.
        self.assertTrue(recall.verify(self.db, p)['valid'])

    def test_changed_raw_blocks_it_and_child(self):
        p = self.packet()
        (self.base/'examples/raw/session-a.md').write_text('changed')
        new = self.packet()
        self.assertFalse(any(h['id'].startswith('session-a') for h in new['hits']))
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_deleted_source(self):
        (self.base/'examples/raw/session-b.md').unlink()
        p = recall.search(self.db, 'API timeout')
        self.assertEqual(p['excluded_sources'][0]['reason'], 'missing')
        self.assertEqual(p['status'], 'no_match')

    def test_tampered_quote(self):
        p = self.packet(); p['hits'][0]['quote'] += 'approved'
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_tampered_metadata(self):
        p = self.packet(); p['hits'][0]['provenance'] = 'transcript'
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_tampered_parent(self):
        p = recall.search(self.db, '部署', kinds=['structured'])
        p['hits'][0]['raw_parent']['id'] = 'invented'
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_invalid_line_range(self):
        p = self.packet(); p['hits'][0]['start_line'] = -1
        self.assertFalse(recall.verify(self.db, p)['valid'])

    def test_missing_parent_rejected_without_replacing_index(self):
        before = self.db.read_bytes()
        m = recall.read_json(self.manifest); m['sources'][1]['raw_id'] = 'absent'
        self.manifest.write_text(json.dumps(m))
        with self.assertRaises(ValueError): recall.build(self.manifest, self.db)
        self.assertEqual(before, self.db.read_bytes())

    def test_index_cannot_overwrite_source(self):
        with self.assertRaises(ValueError):
            recall.build(self.manifest, self.base/'examples/raw/session-a.md')

    def test_output_cannot_overwrite_existing_file(self):
        with self.assertRaises(ValueError): recall.fresh_output(self.manifest)

    def test_reconstructed_label_not_upgraded(self):
        m = recall.read_json(self.manifest); m['sources'][0]['provenance'] = 'reconstructed'
        self.manifest.write_text(json.dumps(m)); self.db = self.base/'index-v2.sqlite'
        recall.build(self.manifest, self.db)
        self.assertEqual(self.packet()['hits'][0]['provenance'], 'reconstructed')

    def test_invalid_packet_and_query(self):
        with self.assertRaises(ValueError): recall.verify(self.db, {})
        with self.assertRaises(ValueError): recall.search(self.db, '')
        with self.assertRaises(ValueError): recall.search(self.db, 'api', limit=0)

    def test_html_escapes_source(self):
        p = self.packet(); p['hits'][0]['quote'] = '<script>alert(1)</script>'
        html = recall.render(p)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_existing_unrelated_file_is_preserved(self):
        dest = self.base/'important.txt'; dest.write_text('keep')
        with self.assertRaises(ValueError): recall.build(self.manifest, dest)
        self.assertEqual(dest.read_text(), 'keep')

    def test_existing_database_is_preserved(self):
        before = self.db.read_bytes()
        with self.assertRaises(ValueError): recall.build(self.manifest, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_atomic_publish_does_not_replace_late_file(self):
        out = self.base/'late.json'; recall.fresh_output(out); out.write_text('keep')
        with self.assertRaises(FileExistsError): recall.atomic_json(out, {'oops': 1})
        self.assertEqual(out.read_text(), 'keep')

    def test_verify_does_not_reread_text_after_hash(self):
        p = recall.search(self.db, 'API', kinds=['raw'])
        # The previous implementation hashed bytes and then read text independently.
        with patch.object(Path, 'read_text', side_effect=AssertionError('second read')):
            self.assertTrue(recall.verify(self.db, p)['valid'])

    def test_source_filter(self):
        p = recall.search(self.db, '部署', source_id='session-a-raw')
        self.assertEqual([h['id'] for h in p['hits']], ['session-a-raw'])


if __name__ == '__main__':
    unittest.main()
