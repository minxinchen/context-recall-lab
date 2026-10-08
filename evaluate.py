#!/usr/bin/env python3
"""Reproducible fixture evaluation; these are authored examples, not a benchmark."""
from pathlib import Path
import json
import tempfile
import recall

CASES = [
    ('freeze', '部署 凍結', 'session-a-raw'),
    ('budget', '預算 成交 價格', 'session-a-raw'),
    ('api', 'API timeout', 'session-b-raw'),
    ('chinese', '測試環境', 'session-b-raw'),
    ('absent', 'volcano_xyz_827361', None),
]


def run():
    rows = []
    with tempfile.TemporaryDirectory() as temp:
        db = Path(temp)/'index.sqlite'
        recall.build(Path(__file__).parent/'examples/manifest.json', db)
        for cid, query, expected in CASES:
            p = recall.search(db, query)
            found = any(h['id'] == expected for h in p['hits']) if expected else not p['hits']
            citations = recall.verify(db, p) if p['hits'] else None
            rows.append({'id': cid, 'expected_found': found,
                         'citations_valid': citations['valid'] if citations else None})
    return {'dataset': 'authored-synthetic-v1', 'cases': rows,
            'passed': sum(r['expected_found'] and r['citations_valid'] is not False for r in rows),
            'total': len(rows), 'limitation': 'Development fixtures, not independent semantic evaluation.'}


if __name__ == '__main__':
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['passed'] == result['total'] else 1)
