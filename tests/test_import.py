import json
from pathlib import Path
import tempfile
import unittest
import import_context
import recall


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.source = self.base/'context'
        (self.source/'raw').mkdir(parents=True); (self.source/'structured').mkdir()
        (self.source/'raw/a.raw.md').write_text('原始對話')
        (self.source/'structured/a.structured.md').write_text('---\nstatus: unresolved\n---\n摘要')

    def test_preserves_sources_and_conservative_metadata(self):
        (self.source/'metrics.jsonl').write_text(json.dumps({'task_id':'a','final_verdict':'pass'})+'\n')
        before = {str(p): p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        result = import_context.prepare(self.source, self.base/'run')
        self.assertEqual(result['structured_review_counts'], {'unknown':1})
        self.assertEqual(result['review_conflicts'][0]['metrics'],'pass')
        rows = recall.read_json(self.base/'run/manifest.json')['sources']
        self.assertTrue(all(r['provenance']=='unknown' for r in rows))
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.source.rglob('*') if p.is_file()})

    def test_orphan_summary_excluded(self):
        (self.source/'structured/orphan.structured.md').write_text('無來源')
        result = import_context.prepare(self.source,self.base/'run')
        self.assertEqual(result['orphan_structured'],['orphan'])
        self.assertEqual(result['index']['sources'],2)

    def test_existing_output_refused(self):
        dest = self.base/'run'; dest.mkdir(); (dest/'keep').write_text('keep')
        with self.assertRaises(ValueError): import_context.prepare(self.source,dest)
        self.assertEqual((dest/'keep').read_text(),'keep')

    def test_body_status_is_not_metadata(self):
        (self.source/'structured/a.structured.md').write_text('---\nstatus: pass\n---\n範例：status: unresolved')
        (self.source/'metrics.jsonl').write_text(json.dumps({'task_id':'a','final_verdict':'pass'})+'\n')
        result = import_context.prepare(self.source,self.base/'run')
        self.assertEqual(result['structured_review_counts'],{'pass':1})
        self.assertEqual(result['review_conflicts'],[])
