#!/usr/bin/env python3
"""
Fetch news from RSS feeds.
Reads feed URLs from configs/companies.yml (company RSS) and configs/feeds.yml (industry media).
"""

import json
import xml.etree.ElementTree as ET
import requests
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent


def load_feeds() -> dict[str, str]:
    """Load RSS feeds from config files."""
    feeds = {}

    # 1. Company RSS feeds from companies.yml
    try:
        import yaml
        companies_file = BASE_DIR / "configs" / "companies.yml"
        if companies_file.exists():
            with open(companies_file) as f:
                config = yaml.safe_load(f)
            for company in config.get("companies", []):
                rss_url = company.get("rss_url")
                if rss_url:
                    feeds[company["id"]] = rss_url
    except ImportError:
        # PyYAML not available, skip company feeds
        pass

    # 2. Industry media feeds from feeds.yml
    try:
        import yaml
        feeds_file = BASE_DIR / "configs" / "feeds.yml"
        if feeds_file.exists():
            with open(feeds_file) as f:
                feed_config = yaml.safe_load(f)
            for feed in feed_config.get("feeds", []):
                feeds[feed["id"]] = feed["url"]
    except ImportError:
        pass

    return feeds


def fetch_rss(feed_url: str, feed_name: str) -> list[dict]:
    """Fetch and parse RSS/Atom feed."""
    try:
        response = requests.get(feed_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (compatible; IntelBot/1.0)"
        })
        response.raise_for_status()

        root = ET.fromstring(response.content)
        articles = []

        # RSS 2.0
        for item in root.findall(".//item")[:20]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = item.findtext("description", "")

            if not title or not link:
                continue

            articles.append({
                "source": feed_name,
                "title": title.strip(),
                "url": link.strip(),
                "published_at": pub_date,
                "summary": (description or "")[:500],
                "fetched_at": datetime.utcnow().isoformat() + "Z"
            })

        # Atom fallback
        if not articles:
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall(".//atom:entry", ns)[:20]:
                title = entry.findtext("atom:title", "", ns)
                link_elem = entry.find("atom:link", ns)
                link = link_elem.get("href", "") if link_elem is not None else ""
                pub_date = (entry.findtext("atom:published", "", ns)
                            or entry.findtext("atom:updated", "", ns))
                summary = entry.findtext("atom:summary", "", ns)

                if not title or not link:
                    continue

                articles.append({
                    "source": feed_name,
                    "title": title.strip(),
                    "url": link.strip(),
                    "published_at": pub_date,
                    "summary": (summary or "")[:500],
                    "fetched_at": datetime.utcnow().isoformat() + "Z"
                })

        return articles

    except Exception as e:
        print(f"  Error fetching {feed_name}: {e}")
        return []


def main():
    today = date.today().isoformat()
    raw_dir = BASE_DIR / "data" / "raw" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    feeds = load_feeds()

    if not feeds:
        print("No RSS feeds configured.")
        print("  Add rss_url to configs/companies.yml")
        print("  or create configs/feeds.yml")
        return

    print(f"Found {len(feeds)} RSS feeds")
    all_articles = []

    for name, url in feeds.items():
        print(f"Fetching {name}...")
        articles = fetch_rss(url, name)
        all_articles.extend(articles)
        print(f"  Got {len(articles)} articles")

    # Deduplicate by URL
    seen = set()
    unique = []
    for a in all_articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    # Save
    output = raw_dir / "rss.jsonl"
    with open(output, "w", encoding="utf-8") as f:
        for article in unique:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(unique)} unique articles to {output}")


if __name__ == "__main__":
    main()
