#!/usr/bin/env python3
"""Generate docs/ directory skeleton for an intel repo.

Usage: python scripts/generate_docs_skeleton.py [--repo-path .]
"""

import argparse
import sys
import yaml
from pathlib import Path
from datetime import datetime


REPO_TO_INDUSTRY = {
    'memory-intel': 'MEM', 'steel-intel': 'STL', 'glass-intel': 'GLS',
    'cement-intel': 'CMT', 'housing-intel': 'HSG', 'auto-intel': 'AUT',
    'machinery-intel': 'MCH', 'agri-intel': 'AGR', 'textile-intel': 'TXT',
    'pharma-intel': 'PHR', 'display-intel': 'DSP', 'telecom-intel': 'TLC',
    'food-intel': 'FOD', 'battery-intel': 'BAT', 'solar-intel': 'SLR',
    'hydrogen-intel': 'H2', 'shipping-intel': 'SHP', 'defense-intel': 'DEF',
    'space-intel': 'SPC', 'mineral-intel': 'MIN', 'water-intel': 'WTR',
    'recycle-intel': 'RCY', 'petpack-intel': 'PET',
}

INDUSTRY_ZH = {
    'MEM': '記憶體', 'STL': '鋼鐵', 'GLS': '玻璃', 'CMT': '水泥',
    'HSG': '營建', 'AUT': '汽車', 'MCH': '機械', 'AGR': '農業',
    'TXT': '紡織', 'PHR': '製藥', 'DSP': '面板', 'TLC': '電信',
    'FOD': '食品', 'BAT': '電池', 'SLR': '太陽能', 'H2': '氫能',
    'SHP': '航運', 'DEF': '國防', 'SPC': '太空', 'MIN': '礦物',
    'WTR': '水務', 'RCY': '回收', 'PET': 'PET包裝',
}

LIVE_DOCS = [
    ('capacity-pricing', 'CP', '產能與價格追蹤'),
    ('supply-demand', 'SD', '供需狀態追蹤'),
    ('financial-health', 'FH', '財務健康警示'),
    ('competitor-comparison', 'CC', '競爭對手比較'),
    ('policy-regulatory', 'PO', '政策法規追蹤'),
    ('supply-chain-map', 'SC', '供應鏈圖譜'),
    ('earnings-calendar', 'EC', '財報行事曆'),
]

DAILY_DOCS = [
    ('institutional-flows', 'IF', '法人籌碼追蹤'),
    ('technicals', 'TA', '股價技術面摘要'),
]

WEEKLY_DOCS = [
    ('industry-report', 'WR', '產業週報'),
    ('capacity-pricing', 'CP', '產能與價格追蹤'),
    ('supply-demand', 'SD', '供需狀態追蹤'),
]

MONTHLY_DOCS = [
    ('revenue-analysis', 'RA', '月營收追蹤分析'),
]

QUARTERLY_DOCS = [
    ('financial-health', 'FH', '財務健康警示'),
    ('competitor-comparison', 'CC', '競爭對手比較'),
]

WEEKLY_MIXED = {'CP', 'SD'}
QUARTERLY_MIXED = {'FH', 'CC'}

DISCLAIMER = ('本文件僅供資訊參考，不構成任何投資建議。'
              '所有內容均來自公開資訊，本平台不對其準確性、完整性或即時性做任何保證。'
              '投資人應自行判斷並承擔投資風險。')


def write_file(path, content):
    """Write file only if it doesn't already exist."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True


def make_merge_yaml(doc_id, title_zh, md_filename, **extra):
    """Generate merge.yaml content."""
    data = {'document_id': doc_id, 'title_zh': title_zh, 'main': {'zh': md_filename}}
    data.update(extra)
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def make_placeholder_md(title):
    """Generate minimal placeholder markdown."""
    return f'# {title}\n\n> {DISCLAIMER}\n\n## 內容\n\n（待生成）\n'


def get_periods():
    """Get current date-based period strings."""
    now = datetime.now()
    return {
        'date': now.strftime('%Y-%m-%d'),
        'week': f"{now.year}-W{now.isocalendar()[1]:02d}",
        'month': now.strftime('%Y-%m'),
        'quarter': f"{now.year}-Q{(now.month - 1) // 3 + 1}",
    }


def load_companies(repo_path):
    """Load company list from configs/companies.yml."""
    config_path = repo_path / 'configs' / 'companies.yml'
    if not config_path.exists():
        print(f'  WARNING: {config_path} not found, skipping companies/')
        return []
    data = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    result = []
    for c in data.get('companies', []):
        cid = c.get('id')
        if not cid:
            continue
        name = c.get('name', cid)
        aliases = c.get('aliases', [])
        zh_name = aliases[0] if aliases else name
        result.append({'id': cid, 'name': name, 'zh_name': zh_name})
    return result


def generate(repo_path):
    repo_path = Path(repo_path).resolve()
    repo_name = repo_path.name

    if repo_name not in REPO_TO_INDUSTRY:
        print(f'ERROR: Unknown repo "{repo_name}". Expected one of: {", ".join(sorted(REPO_TO_INDUSTRY))}')
        sys.exit(1)

    ind = REPO_TO_INDUSTRY[repo_name]
    zh = INDUSTRY_ZH[ind]
    docs = repo_path / 'docs'
    periods = get_periods()
    created = 0

    # Handle existing architecture.md
    arch = docs / 'architecture.md'
    if arch.exists():
        dest = repo_path / 'dev-docs'
        dest.mkdir(exist_ok=True)
        if (dest / 'architecture.md').exists():
            print(f'  WARNING: dev-docs/architecture.md already exists, skipping migration')
        else:
            arch.rename(dest / 'architecture.md')
            print(f'  Moved docs/architecture.md -> dev-docs/architecture.md')

    # --- live/ ---
    for dirname, tc, title in LIVE_DOCS:
        d = docs / 'live' / dirname
        doc_id = f'{tc}-{ind}-LIVE'
        t = f'{zh}{title}（最新版）'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, f'{title}.md')):
            created += 1
        write_file(d / f'{title}.md', make_placeholder_md(t))

    # --- daily/ ---
    for dirname, tc, title in DAILY_DOCS:
        d = docs / 'daily' / periods['date'] / dirname
        doc_id = f'{tc}-{ind}-{periods["date"]}'
        t = f'{zh}{title} {periods["date"]}'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, f'{title}.md')):
            created += 1
        write_file(d / f'{title}.md', make_placeholder_md(t))

    # --- weekly/ ---
    for dirname, tc, title in WEEKLY_DOCS:
        d = docs / 'weekly' / periods['week'] / dirname
        doc_id = f'{tc}-{ind}-{periods["week"]}'
        t = f'{zh}{title} {periods["week"]}'
        extra = {}
        if tc in WEEKLY_MIXED:
            extra['live_ref'] = f'{tc}-{ind}-LIVE'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, f'{title}.md', **extra)):
            created += 1
        write_file(d / f'{title}.md', make_placeholder_md(t))

    # Update live/ latest_snapshot for weekly mixed-mode
    for dirname, tc, _ in WEEKLY_DOCS:
        if tc not in WEEKLY_MIXED:
            continue
        live_yaml = docs / 'live' / dirname / 'merge.yaml'
        if live_yaml.exists():
            data = yaml.safe_load(live_yaml.read_text(encoding='utf-8'))
            data['latest_snapshot'] = f'{tc}-{ind}-{periods["week"]}'
            live_yaml.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding='utf-8')

    # --- monthly/ ---
    for dirname, tc, title in MONTHLY_DOCS:
        d = docs / 'monthly' / periods['month'] / dirname
        doc_id = f'{tc}-{ind}-{periods["month"]}'
        t = f'{zh}{title} {periods["month"]}'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, f'{title}.md')):
            created += 1
        write_file(d / f'{title}.md', make_placeholder_md(t))

    # --- quarterly/ ---
    for dirname, tc, title in QUARTERLY_DOCS:
        d = docs / 'quarterly' / periods['quarter'] / dirname
        doc_id = f'{tc}-{ind}-{periods["quarter"]}'
        t = f'{zh}{title} {periods["quarter"]}'
        extra = {}
        if tc in QUARTERLY_MIXED:
            extra['live_ref'] = f'{tc}-{ind}-LIVE'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, f'{title}.md', **extra)):
            created += 1
        write_file(d / f'{title}.md', make_placeholder_md(t))

    # Update live/ latest_snapshot for quarterly mixed-mode
    for dirname, tc, _ in QUARTERLY_DOCS:
        if tc not in QUARTERLY_MIXED:
            continue
        live_yaml = docs / 'live' / dirname / 'merge.yaml'
        if live_yaml.exists():
            data = yaml.safe_load(live_yaml.read_text(encoding='utf-8'))
            data['latest_snapshot'] = f'{tc}-{ind}-{periods["quarter"]}'
            live_yaml.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False), encoding='utf-8')

    # --- companies/ ---
    companies = load_companies(repo_path)
    for company in companies:
        company_dir = company['id'].replace('_', '-')
        d = docs / 'companies' / company_dir / 'profile'
        doc_id = f'PR-{ind}-{company_dir.upper()}'
        t = f'{company["zh_name"]}（{company["name"]}）'
        md_name = f'{company["zh_name"]}.md'
        if write_file(d / 'merge.yaml', make_merge_yaml(doc_id, t, md_name)):
            created += 1
        write_file(d / md_name, make_placeholder_md(t))

    # --- regulatory-archive/ (empty) ---
    (docs / 'regulatory-archive').mkdir(parents=True, exist_ok=True)

    print(f'Generated {created} documents in {docs}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate docs/ skeleton for intel repo')
    parser.add_argument('--repo-path', default='.', help='Path to intel repo (default: current directory)')
    args = parser.parse_args()
    generate(args.repo_path)
