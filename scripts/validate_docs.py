#!/usr/bin/env python3
"""Validate docs/ directory structure and merge.yaml files.

Usage: python scripts/validate_docs.py [--docs-path docs/]
Checks: 11 items per design spec.
Exit code: 0 if all pass, 1 if any errors.
"""

import argparse
import re
import sys
import yaml
from pathlib import Path


VALID_TOP_DIRS = {
    'daily', 'weekly', 'monthly', 'quarterly',
    'live', 'companies', 'regulatory-archive',
}

VALID_TYPE_CODES = {
    'WR', 'RA', 'IF', 'TA', 'CP', 'SD',
    'FH', 'CC', 'SC', 'PR', 'EC', 'PO', 'PA',
}

FORBIDDEN_PHRASES = [
    '建議買入', '建議賣出', '建議加碼', '建議減碼',
    '推薦買入', '推薦賣出', '推薦加碼', '推薦減碼',
    '目標價',
]

DOC_ID_PATTERN = re.compile(
    r'^(' + '|'.join(VALID_TYPE_CODES) + r')-[A-Z0-9]{2,3}-.+$'
)

COMPANY_DIR_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]*$')


class Validator:
    def __init__(self, docs_path):
        self.docs_path = Path(docs_path)
        self.errors = []
        self.doc_count = 0
        self.document_ids = {}
        self._live_refs = {}
        self._latest_snapshots = {}

    def error(self, rel_path, msg):
        self.errors.append(f'{rel_path} — {msg}')

    def validate(self):
        if not self.docs_path.is_dir():
            self.error('docs/', 'directory does not exist')
            return self.errors

        self.check_top_level_dirs()
        self.check_all_documents()
        self.check_document_id_uniqueness()
        self.check_live_refs_bidirectional()
        return self.errors

    def check_top_level_dirs(self):
        for item in self.docs_path.iterdir():
            if item.is_dir() and item.name not in VALID_TOP_DIRS:
                self.error(f'docs/{item.name}/', 'invalid top-level directory')

    def find_leaf_dirs(self):
        for dirpath in sorted(self.docs_path.rglob('*')):
            if not dirpath.is_dir():
                continue
            subdirs = [d for d in dirpath.iterdir() if d.is_dir()]
            if not subdirs:
                yield dirpath

    def check_all_documents(self):
        for leaf_dir in self.find_leaf_dirs():
            rel = leaf_dir.relative_to(self.docs_path)
            merge_path = leaf_dir / 'merge.yaml'

            if not merge_path.exists():
                if str(rel) == 'regulatory-archive':
                    continue
                self.error(f'{rel}/', 'missing merge.yaml')
                continue

            self.doc_count += 1

            try:
                data = yaml.safe_load(merge_path.read_text(encoding='utf-8'))
            except yaml.YAMLError as e:
                self.error(f'{rel}/merge.yaml', f'invalid YAML: {e}')
                continue

            if not isinstance(data, dict):
                self.error(f'{rel}/merge.yaml', 'YAML root must be a mapping')
                continue

            doc_id = data.get('document_id')
            title_zh = data.get('title_zh')
            main = data.get('main', {})
            main_zh = main.get('zh') if isinstance(main, dict) else None

            if not doc_id:
                self.error(f'{rel}/merge.yaml', 'missing field: document_id')
            if not title_zh:
                self.error(f'{rel}/merge.yaml', 'missing field: title_zh')
            if not main_zh:
                self.error(f'{rel}/merge.yaml', 'missing field: main.zh')

            if not doc_id:
                continue

            if not DOC_ID_PATTERN.match(doc_id):
                self.error(f'{rel}/merge.yaml', f'invalid document_id format: {doc_id}')

            if main_zh:
                md_path = leaf_dir / main_zh
                if not md_path.exists():
                    self.error(f'{rel}/merge.yaml', f'main.zh points to non-existent file: {main_zh}')

            prefix = doc_id.split('-')[0] if '-' in doc_id else ''
            if prefix and prefix not in VALID_TYPE_CODES:
                self.error(f'{rel}/merge.yaml', f'invalid type code in document_id: {prefix}')

            explicit_type = data.get('type')
            if explicit_type and explicit_type != prefix:
                self.error(f'{rel}/merge.yaml',
                           f'type field "{explicit_type}" does not match document_id prefix "{prefix}"')

            parts = str(rel).split('/')
            if parts[0] == 'companies' and len(parts) >= 2:
                company_dir = parts[1]
                if not COMPANY_DIR_PATTERN.match(company_dir):
                    self.error(f'{rel}/merge.yaml',
                               f'company directory name must match [a-z0-9-]+: {company_dir}')

            if main_zh:
                md_path = leaf_dir / main_zh
                if md_path.exists():
                    content = md_path.read_text(encoding='utf-8')
                    for phrase in FORBIDDEN_PHRASES:
                        if phrase in content:
                            self.error(f'{rel}/{main_zh}',
                                       f'contains forbidden investment phrase: "{phrase}"')

            self.document_ids[doc_id] = str(rel)

            live_ref = data.get('live_ref')
            if live_ref:
                self._live_refs[doc_id] = live_ref

            latest_snap = data.get('latest_snapshot')
            if latest_snap:
                self._latest_snapshots[doc_id] = latest_snap

    def check_document_id_uniqueness(self):
        seen = {}
        for doc_id, rel_path in self.document_ids.items():
            if doc_id in seen:
                self.error(f'{rel_path}/merge.yaml',
                           f'duplicate document_id: {doc_id} (also in {seen[doc_id]}/)')
            else:
                seen[doc_id] = rel_path

    def check_live_refs_bidirectional(self):
        for snap_id, live_id in self._live_refs.items():
            if live_id not in self.document_ids:
                snap_path = self.document_ids.get(snap_id, '?')
                self.error(f'{snap_path}/merge.yaml',
                           f'live_ref points to non-existent document: {live_id}')

        for live_id, snap_id in self._latest_snapshots.items():
            if snap_id not in self.document_ids:
                live_path = self.document_ids.get(live_id, '?')
                self.error(f'{live_path}/merge.yaml',
                           f'latest_snapshot points to non-existent document: {snap_id}')

        for live_id, snap_id in self._latest_snapshots.items():
            if snap_id in self._live_refs:
                expected_live = self._live_refs[snap_id]
                if expected_live != live_id:
                    live_path = self.document_ids.get(live_id, '?')
                    self.error(f'{live_path}/merge.yaml',
                               f'latest_snapshot {snap_id} has live_ref pointing to '
                               f'{expected_live}, not {live_id}')


def main():
    parser = argparse.ArgumentParser(description='Validate docs/ structure')
    parser.add_argument('--docs-path', default='docs', help='Path to docs/ directory')
    args = parser.parse_args()

    v = Validator(args.docs_path)
    errors = v.validate()

    repo_name = Path('.').resolve().name

    if errors:
        print(f'[FAIL] {repo_name}: {v.doc_count} documents, {len(errors)} errors')
        for e in errors:
            print(f'  ERROR: {e}')
        sys.exit(1)
    else:
        print(f'[PASS] {repo_name}: {v.doc_count} documents, 0 errors')
        sys.exit(0)


if __name__ == '__main__':
    main()
