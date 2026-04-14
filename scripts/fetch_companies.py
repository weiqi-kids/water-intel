#!/usr/bin/env python3
"""
Fetch IR and news from company websites.
Uses company-specific fetchers.
"""

import json
import sys
from datetime import date
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from fetchers import SamsungFetcher, SKHynixFetcher
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure requests and beautifulsoup4 are installed")
    sys.exit(1)


def main():
    today = date.today().isoformat()
    raw_dir = Path(__file__).parent.parent / "data" / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    all_documents = []

    # List of fetchers to run
    fetchers = [
        SamsungFetcher(),
        SKHynixFetcher(),
        # Add more fetchers here as they are implemented
    ]

    for fetcher in fetchers:
        print(f"\n=== Fetching {fetcher.company_name} ===")

        try:
            result = fetcher.fetch_all()

            for doc_type, docs in result.items():
                print(f"  {doc_type}: {len(docs)} documents")
                for doc in docs:
                    all_documents.append(doc.to_dict())

        except Exception as e:
            print(f"  Error: {e}")

    # Save raw documents
    with open(raw_dir / "companies.jsonl", "w", encoding="utf-8") as f:
        for doc in all_documents:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(all_documents)} documents to {raw_dir / 'companies.jsonl'}")


if __name__ == "__main__":
    main()
