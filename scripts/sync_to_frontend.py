#!/usr/bin/env python3
"""
同步事件到前端

從 data/events/*.jsonl 讀取標準格式事件，
轉換為前端格式並輸出到 site/data/events.json

用法：
    python scripts/sync_to_frontend.py
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
EVENTS_DIR = BASE_DIR / "data" / "events"
OUTPUT_FILE = BASE_DIR / "site" / "data" / "events.json"


def load_all_events() -> list[dict]:
    """載入所有事件"""
    events = []

    if not EVENTS_DIR.exists():
        print(f"警告：{EVENTS_DIR} 不存在")
        return events

    for jsonl_file in sorted(EVENTS_DIR.glob("*.jsonl")):
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

    return events


def convert_to_frontend_format(event: dict) -> dict:
    """
    將標準格式轉換為前端格式

    標準格式：
    {
        "id": "...",
        "date": "...",
        "entities": {"companies": [...], "customers": [...], "suppliers": [...]},
        "topics": [...],
        "sentiment": {"label": "...", "score": 0.0},
        "importance": {"score": 0.5, "reasons": [...]},
        "title": "...",
        "content": "...",
        "sources": [...]
    }

    前端格式：
    {
        "id": "...",
        "date": "...",
        "companies": [...],
        "topics": [...],
        "impact": "neutral",
        "title": "...",
        "summary": "...",
        "sources": [...]
    }
    """
    entities = event.get("entities", {})
    sentiment = event.get("sentiment", {})

    return {
        "id": event.get("id", ""),
        "date": event.get("date", ""),
        "companies": entities.get("companies", []),
        "topics": event.get("topics", []),
        "impact": sentiment.get("label", "neutral"),
        "title": event.get("title", ""),
        "summary": event.get("content", "")[:200] if event.get("content") else "",
        "sources": event.get("sources", []),
    }


def main():
    print("=== 同步事件到前端 ===")

    # 載入所有事件
    events = load_all_events()
    print(f"載入 {len(events)} 則事件")

    # 轉換格式
    frontend_events = [convert_to_frontend_format(e) for e in events]

    # 按日期排序（新到舊）
    frontend_events.sort(key=lambda x: x["date"] or "0000-00-00", reverse=True)

    # 去重（依 ID）
    seen_ids = set()
    unique_events = []
    for event in frontend_events:
        if event["id"] not in seen_ids:
            seen_ids.add(event["id"])
            unique_events.append(event)

    # 存檔
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_events, f, indent=2, ensure_ascii=False)

    print(f"輸出 {len(unique_events)} 則事件到 {OUTPUT_FILE}")

    # 統計
    from collections import Counter
    dates = Counter(e["date"] for e in unique_events)
    print(f"\n日期分布（最近 10 天）：")
    for date, count in sorted(dates.items(), reverse=True)[:10]:
        print(f"  {date}: {count} 則")


if __name__ == "__main__":
    main()
