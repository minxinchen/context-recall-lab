#!/usr/bin/env python3
"""Import an existing context_log as a local manifest; never edit its source files."""
import argparse
from collections import Counter
import json
import re
from pathlib import Path
import recall


def frontmatter_status(text):
    """Read only a single, flat status field in a leading fenced header."""
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        return None
    try:
        end = lines.index('---', 1)
    except ValueError:
        return None
    matches = [re.fullmatch(r'status:\s*([a-z_]+)\s*', line) for line in lines[1:end]]
    values = [m.group(1) for m in matches if m]
    return values[0] if len(values) == 1 else None


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('use a new output directory')
    raw = {p.name[:-7]: p for p in (root/'raw').glob('*.raw.md')}
    structured = {p.name[:-14]: p for p in (root/'structured').glob('*.structured.md')}
    if not raw:
        raise ValueError('no raw records found')
    metrics_path = root/'metrics.jsonl'
    metrics = [json.loads(s) for s in metrics_path.read_text().splitlines() if s.strip()] if metrics_path.exists() else []
    metrics_by_id = {}
    for r in metrics:
        metrics_by_id.setdefault(r['task_id'], []).append(r)
    rows = []
    conflicts = []
    for sid, path in sorted(raw.items()):
        rows.append({'id': sid+'-raw', 'path': str(path), 'title': sid,
                     'kind': 'raw', 'provenance': 'unknown', 'review': 'unknown'})
        if sid not in structured:
            continue
        history = metrics_by_id.get(sid, [])
        # Historical rows have no content hash. Preserve the declared state, never upgrade it.
        declared = history[-1].get('final_verdict', 'unknown') if history else 'unknown'
        if declared not in ('pass', 'unresolved'):
            declared = 'unknown'
        fm = frontmatter_status(structured[sid].read_text(encoding='utf-8'))
        if fm is not None and declared != 'unknown' and fm != declared:
            conflicts.append({'id':sid, 'metrics':declared, 'frontmatter':fm})
            declared = 'unknown'
        elif declared == 'unknown' and fm in ('pass','unresolved'):
            declared = fm
        rows.append({'id': sid+'-structured', 'path': str(structured[sid]), 'title': sid,
                     'kind': 'structured', 'provenance': 'unknown', 'review': declared,
                     'raw_id': sid+'-raw'})
    output.mkdir(parents=True)
    manifest = output/'manifest.json'
    recall.atomic_json(manifest, {'version': 1, 'sources': rows})
    report = {'raw_files': len(raw), 'structured_files': len(structured),
              'paired': len(raw.keys() & structured.keys()),
              'orphan_raw': sorted(raw.keys()-structured.keys()),
              'orphan_structured': sorted(structured.keys()-raw.keys()),
              'metrics_rows': len(metrics),
              'duplicate_metric_ids': sorted(k for k,v in metrics_by_id.items() if len(v)>1),
              'review_conflicts': conflicts,
              'structured_review_counts': dict(Counter(r['review'] for r in rows if r['kind']=='structured')),
              'provenance_policy': 'unknown: a raw filename does not establish transcript authenticity',
              'review_policy': 'historical declarations, not bound to current file hashes',
              'index': recall.build(manifest, output/'index.sqlite')}
    recall.atomic_json(output/'audit.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('context_log'); p.add_argument('output')
    a = p.parse_args()
    print(json.dumps(prepare(a.context_log,a.output), ensure_ascii=False, indent=2))
