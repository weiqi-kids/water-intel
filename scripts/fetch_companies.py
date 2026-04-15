#!/usr/bin/env python3
"""
Fetch IR and news from company websites using Playwright.
Gracefully skips if no fetcher modules are available.
"""

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from fetchers import FETCHERS
except (ImportError, ModuleNotFoundError):
    FETCHERS = {}


def main():
    if not FETCHERS:
        print("No fetcher modules configured. RSS feeds are the primary news source.")
        print("To add Playwright fetchers, create modules in fetchers/ directory.")
        return

    today = date.today().isoformat()
    raw_dir = Path(__file__).parent.parent / "data" / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_documents = []

    for company_id, fetcher_class in FETCHERS.items():
        print(f"\n=== Fetching {company_id} ===")
        try:
            fetcher = fetcher_class()
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
