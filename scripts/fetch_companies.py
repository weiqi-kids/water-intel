#!/usr/bin/env python3
"""
Fetch IR and news from company websites.
Reads fetch_mode and ir_rss_url from configs/companies.yml per company.
Supports three modes: rss (IR RSS feed), http (plain HTTP), playwright (JS rendering).
"""

import json
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from fetchers import FETCHERS
except (ImportError, ModuleNotFoundError, SyntaxError):
    FETCHERS = {}

BASE = Path(__file__).parent.parent


def load_companies_config() -> dict:
    """Load companies.yml and return a dict keyed by company id."""
    config_file = BASE / "configs" / "companies.yml"
    if not config_file.exists():
        return {}
    with open(config_file, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {c["id"]: c for c in data.get("companies", [])}


def main():
    companies_config = load_companies_config()

    if not FETCHERS and not companies_config:
        print("No fetcher modules or company configs found.")
        return

    today = date.today().isoformat()
    raw_dir = BASE / "data" / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_documents = []

    for company_id, fetcher_class in FETCHERS.items():
        config = companies_config.get(company_id, {})
        fetch_mode = config.get("fetch_mode", "http")
        ir_rss_url = config.get("ir_rss_url")

        print(f"\n=== Fetching {company_id} (mode={fetch_mode}) ===")
        try:
            fetcher = fetcher_class()
            fetcher.fetch_mode = fetch_mode
            fetcher.ir_rss_url = ir_rss_url
            result = fetcher.fetch_all()
            for doc_type, docs in result.items():
                print(f"  {doc_type}: {len(docs)} documents")
                for doc in docs:
                    all_documents.append(doc.to_dict())
        except Exception as e:
            print(f"  Error: {e}")

    # Also fetch RSS-only companies (not in FETCHERS but have ir_rss_url)
    fetched_ids = set(FETCHERS.keys())
    for company_id, config in companies_config.items():
        if company_id in fetched_ids:
            continue
        ir_rss_url = config.get("ir_rss_url")
        if not ir_rss_url:
            continue

        print(f"\n=== Fetching {company_id} (rss-only) ===")
        try:
            import importlib.util
            _spec = importlib.util.spec_from_file_location(
                "fetchers_base", str(BASE / "fetchers" / "base.py"))
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            CompanyFetcher = _mod.CompanyFetcher
            CompanyDocument = _mod.CompanyDocument

            class _RssOnlyFetcher(CompanyFetcher):
                def parse_ir(self, html): return []
                def parse_news(self, html): return []

            fetcher = _RssOnlyFetcher()
            fetcher.company_id = company_id
            fetcher.company_name = config.get("name", company_id)
            fetcher.fetch_mode = "rss"
            fetcher.ir_rss_url = ir_rss_url
            result = fetcher.fetch_all()
            for doc_type, docs in result.items():
                print(f"  {doc_type}: {len(docs)} documents")
                for doc in docs:
                    all_documents.append(doc.to_dict())
        except Exception as e:
            print(f"  Error: {e}")

    if all_documents:
        output = raw_dir / "companies.jsonl"
        with open(output, "w", encoding="utf-8") as f:
            for doc in all_documents:
                f.write(json.dumps(doc, ensure_ascii=False) + "\n")
        print(f"\nSaved {len(all_documents)} documents to {output}")
    else:
        print("\nNo documents fetched.")


if __name__ == "__main__":
    main()
