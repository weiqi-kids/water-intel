#!/usr/bin/env python3
"""
Normalize raw data into standard format.
Combines data from multiple sources.
"""

import json
from datetime import date
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file."""
    if not path.exists():
        return []

    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items


def _pick_short_name(company):
    """優先選中文別名作為顯示名稱，沒有則用 name"""
    import re
    aliases = company.get("aliases") or []
    # 找第一個含中文字的 alias
    for a in aliases:
        if a and re.search(r'[\u4e00-\u9fff]', a):
            return a
    # 沒有中文 alias，用 name（可能本身就是中文）
    name = company.get("name", "")
    if re.search(r'[\u4e00-\u9fff]', name):
        return name
    # 都沒有中文，取第一個 alias 或 name
    return aliases[0] if aliases else name


def main():
    today = date.today().isoformat()
    raw_dir = Path(__file__).parent.parent / "data" / "raw" / today
    normalized_dir = Path(__file__).parent.parent / "data" / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    # Combine all news/IR documents
    all_events = []

    # Load company documents
    company_docs = load_jsonl(raw_dir / "companies.jsonl")
    for doc in company_docs:
        all_events.append({
            "id": doc.get("id", ""),
            "date": doc.get("published_at", today)[:10] if doc.get("published_at") else today,
            "companies": [doc.get("company_id", "")],
            "topics": doc.get("tags", []),
            "impact": "neutral",
            "title": doc.get("title", ""),
            "summary": doc.get("content", "")[:200] if doc.get("content") else "",
            "sources": [{
                "type": doc.get("doc_type", "news"),
                "title": doc.get("title", ""),
                "url": doc.get("url", ""),
                "fetchedAt": doc.get("fetched_at", ""),
                "excerpt": doc.get("content", "")[:500] if doc.get("content") else ""
            }]
        })

    # Load RSS articles
    rss_articles = load_jsonl(raw_dir / "rss.jsonl")
    for article in rss_articles:
        all_events.append({
            "id": f"rss-{hash(article.get('url', '')) % 100000}",
            "date": article.get("published_at", today)[:10] if article.get("published_at") else today,
            "companies": [],  # Will be tagged later
            "topics": ["news"],
            "impact": "neutral",
            "title": article.get("title", ""),
            "summary": article.get("summary", "")[:200] if article.get("summary") else "",
            "sources": [{
                "type": "news",
                "title": article.get("title", ""),
                "url": article.get("url", ""),
                "fetchedAt": article.get("fetched_at", ""),
                "excerpt": article.get("summary", "")[:500] if article.get("summary") else ""
            }]
        })

    # Save events
    with open(normalized_dir / "events.json", "w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print(f"Normalized {len(all_events)} events to {normalized_dir / 'events.json'}")

    # Generate companies.json for visualization
    companies_yml = Path(__file__).parent.parent / "configs" / "companies.yml"
    if companies_yml.exists():
        import yaml
        with open(companies_yml, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Convert to visualization format
        viz_companies = []
        viz_links = []

        # Position mapping: role → row
        role_to_row = {
            "設備": "equip",
            "材料": "material",
            "EDA": "eda",
            "IP": "eda",
            "矽晶圓": "material",
            "記憶體製造": "memory",
            "利基記憶體": "memory",
            "控制IC": "controller",
            "記憶體模組": "module",
            "代工": "foundry",
            "封測": "osat",
            "OSAT": "osat",
            "GPU": "ai",
            "GPU/CPU": "ai",
            "AI 晶片": "ai",
            "行動晶片": "ai",
            "網通晶片": "ai",
            "類比IC": "ai",
            "功率半導體": "ai",
            "車用晶片": "ai",
            "系統": "system",
            "消費電子": "system",
            "CSP": "csp",
        }

        row_y = {
            "equip": 0.04,
            "material": 0.13,
            "eda": 0.22,
            "memory": 0.34,
            "controller": 0.43,
            "module": 0.52,
            "foundry": 0.61,
            "osat": 0.70,
            "ai": 0.80,
            "system": 0.89,
            "csp": 0.96,
        }

        # Count companies per row
        from collections import defaultdict
        row_counts = defaultdict(int)
        company_rows = []
        for company in config.get("companies", []):
            role = company.get("role", "")
            row_key = role_to_row.get(role, "memory")
            company_rows.append(row_key)
            row_counts[row_key] += 1

        row_idx = defaultdict(int)

        for i, company in enumerate(config.get("companies", [])):
            role = company.get("role", "")
            row_key = company_rows[i]
            total = row_counts[row_key]
            idx = row_idx[row_key]
            row_idx[row_key] += 1

            x = 0.05 + (idx * 0.9 / max(total - 1, 1)) if total > 1 else 0.5
            y = row_y.get(row_key, 0.5)

            viz_companies.append({
                "id": company.get("id"),
                "name": company.get("name"),
                "short_name": _pick_short_name(company),
                "position": company.get("position", "midstream"),
                "role": role,
                "x": round(x, 3),
                "y": y
            })

            # Add links for downstream relationships
            for downstream_id in company.get("downstream", []):
                viz_links.append({
                    "source": company.get("id"),
                    "target": downstream_id,
                    "strength": 2
                })

        # Build ETF list for visualization
        viz_etfs = []
        for etf in config.get("etfs", []):
            viz_etfs.append({
                "id": f"etf_{etf['id']}",
                "name": etf.get("name", ""),
                "ticker": etf.get("ticker", ""),
                "market": etf.get("market", ""),
                "currency": etf.get("currency", "USD"),
                "description": etf.get("description", ""),
            })

        viz_data = {
            "companies": viz_companies,
            "links": viz_links,
            "etfs": viz_etfs,
        }

        with open(normalized_dir / "companies.json", "w", encoding="utf-8") as f:
            json.dump(viz_data, f, ensure_ascii=False, indent=2)

        print(f"Generated {normalized_dir / 'companies.json'}")


if __name__ == "__main__":
    main()
