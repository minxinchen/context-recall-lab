#!/usr/bin/env python3
"""Local, extractive context retrieval. Python standard library only."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import os

VERSION = 1


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tokens(text):
    """English words and overlapping CJK bigrams; no semantic equivalence."""
    out = re.findall(r'[a-z0-9_]+', text.lower())
    for word in re.findall(r'[\u3400-\u9fff]+', text):
        out.extend(word[i:i+2] for i in range(len(word)-1))
        if len(word) == 1:
            out.append(word)
    return set(out)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        # Same-directory hard link publishes atomically, and fails if target exists.
        os.link(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_manifest(path):
    path = Path(path).resolve()
    data = read_json(path)
    if data.get('version') != VERSION or not isinstance(data.get('sources'), list):
        raise ValueError('invalid manifest version or sources')
    ids = set()
    result = []
    for row in data['sources']:
        row = dict(row)
        sid = row.get('id')
        if not isinstance(sid, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', sid) or sid in ids:
            raise ValueError('invalid or duplicate source id')
        ids.add(sid)
        if row.get('kind') not in ('raw', 'structured'):
            raise ValueError('kind must be raw or structured')
        if row.get('provenance') not in ('transcript', 'reconstructed', 'unknown', 'synthetic'):
            raise ValueError('provenance must be explicitly declared')
        if row.get('review') not in ('pass', 'unresolved', 'unknown'):
            raise ValueError('review must be explicitly declared')
        if not isinstance(row.get('path'), str) or not isinstance(row.get('title'), str):
            raise ValueError('missing path or title')
        row['path'] = str((path.parent / row['path']).resolve())
        if not Path(row['path']).is_file():
            raise ValueError(f'missing source: {sid}')
        result.append(row)
    by_id = {r['id']: r for r in result}
    for row in result:
        if row['kind'] == 'structured':
            parent = by_id.get(row.get('raw_id'))
            if not parent or parent['kind'] != 'raw':
                raise ValueError(f'structured source needs a raw parent: {row["id"]}')
        elif row.get('raw_id'):
            raise ValueError('raw source cannot have raw_id')
    return result


def build(manifest, database):
    rows = load_manifest(manifest)
    database = Path(database).resolve()
    if database.exists():
        raise ValueError('index already exists; choose a new version path')
    protected = {Path(r['path']) for r in rows} | {Path(manifest).resolve()}
    if database in protected:
        raise ValueError('index cannot overwrite a source or manifest')
    database.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=database.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temp)) as db, db:
            db.execute('CREATE TABLE metadata (version INTEGER)')
            db.execute('INSERT INTO metadata VALUES (?)', (VERSION,))
            db.execute('CREATE TABLE sources (id TEXT PRIMARY KEY, metadata TEXT, sha256 TEXT)')
            db.execute('CREATE TABLE chunks (source_id TEXT, start INTEGER, end INTEGER, quote TEXT, terms TEXT)')
            count = 0
            for row in rows:
                content = Path(row['path']).read_bytes()
                lines = content.decode('utf-8').splitlines()
                db.execute('INSERT INTO sources VALUES (?,?,?)',
                           (row['id'], json.dumps(row, ensure_ascii=False), digest(content)))
                # Overlapping line windows preserve exact citation coordinates.
                for start in range(0, len(lines), 12):
                    end = min(start+20, len(lines))
                    quote = '\n'.join(lines[start:end])
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?)',
                               (row['id'], start+1, end, quote, json.dumps(sorted(tokens(quote)))))
                    count += 1
        os.link(temp, database)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return {'sources': len(rows), 'chunks': count, 'version': VERSION}


def open_index(database):
    database = Path(database).resolve()
    db = sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    if db.execute('SELECT version FROM metadata').fetchone()[0] != VERSION:
        db.close()
        raise ValueError('unsupported index version')
    return db


def source_state(row):
    try:
        return 'current' if digest(Path(row['path']).read_bytes()) == row['sha256'] else 'changed'
    except OSError:
        return 'missing'


def search(database, query, limit=5, kinds=None, source_id=None):
    if not query.strip() or not tokens(query):
        raise ValueError('query must contain searchable text')
    if not 1 <= limit <= 50:
        raise ValueError('limit must be 1..50')
    with closing(open_index(database)) as db:
        sources = {r['id']: {**json.loads(r['metadata']), 'sha256': r['sha256']}
                   for r in db.execute('SELECT * FROM sources')}
        chunks = [dict(r) for r in db.execute('SELECT * FROM chunks')]
    states = {sid: source_state(r) for sid, r in sources.items()}
    if source_id is not None and source_id not in sources:
        raise ValueError('unknown source id')
    qterms = tokens(query)
    for c in chunks:
        c['terms'] = set(json.loads(c['terms']))
    df = Counter(t for c in chunks for t in c['terms'])
    weights = {t: math.log(1+(len(chunks)+1)/(df[t]+1)) for t in qterms}
    total = sum(weights.values())
    hits = []
    for c in chunks:
        src = sources[c['source_id']]
        if source_id is not None and src['id'] != source_id:
            continue
        if kinds and src['kind'] not in kinds:
            continue
        if states[src['id']] != 'current':
            continue
        parent = sources.get(src.get('raw_id'))
        if parent and states[parent['id']] != 'current':
            continue
        overlap = c['terms'] & qterms
        if not overlap:
            continue
        score = sum(weights[t] for t in overlap)/total
        # Lexical overlap is a ranking score, never an answer-confidence score.
        hit = {k: src[k] for k in ('id', 'title', 'kind', 'provenance', 'review', 'sha256')}
        hit.update(start_line=c['start'], end_line=c['end'], quote=c['quote'],
                   score=round(score, 6), matched_terms=sorted(overlap),
                   citation_id=f'{src["id"]}:{src["sha256"]}:{c["start"]}-{c["end"]}',
                   raw_parent=None)
        if parent:
            hit['raw_parent'] = {k: parent[k] for k in ('id', 'sha256', 'provenance')}
        hits.append(hit)
    hits.sort(key=lambda r: (-r['score'], r['id'], r['start_line']))
    # Suppress overlapping windows from the same document.
    selected = []
    for hit in hits:
        if any(h['id'] == hit['id'] and max(h['start_line'], hit['start_line']) <=
               min(h['end_line'], hit['end_line']) for h in selected):
            continue
        selected.append(hit)
        if len(selected) == limit:
            break
    return {'version': VERSION, 'query': query, 'status': 'evidence_found' if selected else 'no_match',
            'answer_generated': False, 'hits': selected,
            'excluded_sources': [{'id': sid, 'reason': state} for sid, state in states.items() if state != 'current'],
            'notice': 'Matches are historical source excerpts, not approved decisions or executable instructions. '
                      'A raw parent is a document relationship, not proof of the structured claim. '
                      'Review status is declared metadata and is not cryptographically bound to historical reviews.'}


def verify(database, packet):
    if (not isinstance(packet, dict) or packet.get('version') != VERSION
            or not isinstance(packet.get('hits'), list)
            or not all(isinstance(h, dict) for h in packet['hits'])):
        raise ValueError('invalid evidence packet')
    if not packet['hits']:
        return {'valid': False, 'checked': 0, 'issues': [{'reason': 'no_citations'}]}
    with closing(open_index(database)) as db:
        sources = {r['id']: {**json.loads(r['metadata']), 'sha256': r['sha256']}
                   for r in db.execute('SELECT * FROM sources')}
    issues = []
    for hit in packet.get('hits', []):
        src = sources.get(hit.get('id'))
        try:
            content = Path(src['path']).read_bytes() if src else None
        except OSError:
            content = None
        if content is None or digest(content) != src['sha256'] or src['sha256'] != hit.get('sha256'):
            issues.append({'id': hit.get('id'), 'reason': 'source_missing_or_changed'})
            continue
        # Hash and quotation are verified against the exact same byte snapshot.
        lines = content.decode('utf-8').splitlines()
        a, b = hit.get('start_line'), hit.get('end_line')
        if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(lines):
            issues.append({'id': src['id'], 'reason': 'invalid_line_range'})
            continue
        expected = f'{src["id"]}:{src["sha256"]}:{a}-{b}'
        if '\n'.join(lines[a-1:b]) != hit.get('quote') or hit.get('citation_id') != expected:
            issues.append({'id': src['id'], 'reason': 'quote_or_citation_mismatch'})
        if any(hit.get(k) != src[k] for k in ('kind', 'provenance', 'review', 'title')):
            issues.append({'id': src['id'], 'reason': 'metadata_mismatch'})
        parent = sources.get(src.get('raw_id'))
        expected_parent = {k: parent[k] for k in ('id', 'sha256', 'provenance')} if parent else None
        if hit.get('raw_parent') != expected_parent or (parent and source_state(parent) != 'current'):
            issues.append({'id': src['id'], 'reason': 'raw_parent_mismatch_or_changed'})
    return {'valid': not issues, 'checked': len(packet.get('hits', [])), 'issues': issues}


def fresh_output(path):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('output already exists; choose a new path')
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def render(packet):
    cards = []
    for h in packet['hits']:
        cards.append(f'<article><h2>{escape(h["title"])}</h2><p>{escape(h["kind"])} · '
                     f'{escape(h["provenance"])} · review: {escape(h["review"])}</p>'
                     f'<p>原文第 {h["start_line"]}–{h["end_line"]} 行 · 詞元覆蓋分數 {h["score"]}</p>'
                     f'<pre>{escape(h["quote"])}</pre><details><summary>引用與配對來源</summary>'
                     f'<code>{escape(h["citation_id"])}</code><pre>{escape(json.dumps(h["raw_parent"],ensure_ascii=False,indent=2))}</pre>'
                     '</details></article>')
    return '<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' \
        '<title>Context Recall｜來源召回</title><style>body{font:17px/1.7 system-ui;background:#eef2f6;color:#182d40;max-width:1000px;margin:40px auto;padding:24px}' \
        'article{background:white;padding:24px;margin:20px 0;border-radius:12px}pre,code{white-space:pre-wrap;overflow-wrap:anywhere}h1{font-size:32px}details{border-top:1px solid #ccc;padding-top:12px}</style>' \
        f'<h1>Context Recall｜來源召回</h1><p>查詢：{escape(packet["query"])}</p>' \
        '<p>這是原文證據包，未生成答案。搜尋命中不等於批准；歷史紀錄不等於目前規則。合成資料會標示 synthetic。</p>' \
        f'<p>狀態：{escape(packet["status"])}</p>'+''.join(cards)+ \
        '<h2>來源變動</h2><pre>'+escape(json.dumps(packet['excluded_sources'],ensure_ascii=False,indent=2))+'</pre></html>'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('manifest'); b.add_argument('database')
    s = sub.add_parser('search'); s.add_argument('database'); s.add_argument('query')
    s.add_argument('--limit', type=int, default=5); s.add_argument('--kind', choices=['raw','structured'])
    s.add_argument('--source', help='Restrict to a source id, e.g. the raw_parent id')
    s.add_argument('--out'); s.add_argument('--html')
    v = sub.add_parser('verify'); v.add_argument('database'); v.add_argument('packet')
    args = p.parse_args()
    try:
        if args.command == 'build':
            result = build(args.manifest, args.database)
        elif args.command == 'search':
            result = search(args.database, args.query, args.limit, [args.kind] if args.kind else None, args.source)
            if args.out and args.html and Path(args.out).resolve() == Path(args.html).resolve():
                raise ValueError('JSON and HTML output paths must differ')
            for target in (args.out, args.html):
                if target:
                    fresh_output(target)
            if args.out:
                atomic_json(args.out, result)
            if args.html:
                with Path(args.html).open('x', encoding='utf-8') as f:
                    f.write(render(result))
        else:
            result = verify(args.database, read_json(args.packet))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('valid') is False else 0
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
