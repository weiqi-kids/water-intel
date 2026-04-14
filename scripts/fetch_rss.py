#!/usr/bin/env python3
"""
Fetch news from RSS feeds.
"""

import json
import sys
from datetime import date
from pathlib import Path

# Add templates to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "templates"))

try:
    from fetchers.news import create_fetcher, PRESET_FEEDS
except ImportError:
    # Fallback: define feeds here
    PRESET_FEEDS = {
        "digitimes": "https://www.digitimes.com/rss/rss_tw.xml",
        "techcrunch_ai": "https://techcrunch.com/tag/artificial-intelligence/feed/",
    }
    create_fetcher = None


def fetch_rss_simple(feed_url: str, feed_name: str) -> list[dict]:
    """Simple RSS fetch without feedparser."""
    import xml.etree.ElementTree as ET
    import requests
    from datetime import datetime

    try:
        response = requests.get(feed_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; MemoryIntel/1.0)"
        })
        response.raise_for_status()

        root = ET.fromstring(response.content)
        articles = []

        # Try RSS 2.0 format
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")

            articles.append({
                "source": feed_name,
                "title": title,
                "url": link,
                "published_at": pub_date,
                "summary": description[:500] if description else None,
                "fetched_at": datetime.utcnow().isoformat() + "Z"
            })

        # Try Atom format if no items found
        if not articles:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns)[:20]:
                title = entry.findtext("atom:title", "", ns)
                link_elem = entry.find("atom:link", ns)
                link = link_elem.get("href", "") if link_elem is not None else ""
                pub_date = entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns)
                summary = entry.findtext("atom:summary", "", ns)

                articles.append({
                    "source": feed_name,
                    "title": title,
                    "url": link,
                    "published_at": pub_date,
                    "summary": summary[:500] if summary else None,
                    "fetched_at": datetime.utcnow().isoformat() + "Z"
                })

        return articles

    except Exception as e:
        print(f"  Error fetching {feed_name}: {e}")
        return []


def main():
    today = date.today().isoformat()
    raw_dir = Path(__file__).parent.parent / "data" / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Memory/semiconductor focused feeds
    feeds = {
        "semiengineering": "https://semiengineering.com/feed/",
        "digitimes": "https://www.digitimes.com/rss/rss.xml",
        "tomshardware_memory": "https://www.tomshardware.com/feeds/tag/memory",
        "tomshardware_storage": "https://www.tomshardware.com/feeds/tag/storage",
    }

    all_articles = []

    for name, url in feeds.items():
        print(f"Fetching {name}...")

        if create_fetcher:
            try:
                fetcher = create_fetcher(name, url)
                articles = fetcher.fetch()
                for article in articles:
                    all_articles.append(article.to_dict())
                print(f"  Got {len(articles)} articles")
            except Exception as e:
                print(f"  Error: {e}")
        else:
            articles = fetch_rss_simple(url, name)
            all_articles.extend(articles)
            print(f"  Got {len(articles)} articles")

    # Save
    with open(raw_dir / "rss.jsonl", "w", encoding="utf-8") as f:
        for article in all_articles:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(all_articles)} articles to {raw_dir / 'rss.jsonl'}")


if __name__ == "__main__":
    main()
