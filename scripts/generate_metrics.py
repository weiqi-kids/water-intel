#!/usr/bin/env python3
"""
每日指標計算腳本

功能：
1. 讀取今日事件
2. 計算各公司、各主題的統計
3. 載入歷史基準線
4. 輸出 data/metrics/{date}.json

用法：
    python scripts/generate_metrics.py --date 2026-03-14
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def load_events(events_file: Path) -> list[dict]:
    """載入事件（JSONL 格式）"""
    if not events_file.exists():
        return []

    events = []
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    return events


def load_baselines(baselines_dir: Path) -> dict:
    """
    載入歷史基準線

    Returns:
        {
            "companies": {
                "samsung": {
                    "7d_avg": float,
                    "30d_avg": float,
                    "yoy_same_week": int,
                    "sentiment_7d_avg": float,
                    "sentiment_30d_avg": float,
                    "data_days": int,
                },
                ...
            },
            "topics": {
                "hbm": {
                    "7d_avg": float,
                    "30d_avg": float,
                    "yoy_same_week": int,
                    "sentiment_7d_avg": float,
                    "sentiment_30d_avg": float,
                    "last_seen": "YYYY-MM-DD",
                    "data_days": int,
                },
                ...
            }
        }
    """
    baselines_file = baselines_dir / "baselines.json"
    if not baselines_file.exists():
        return {"companies": {}, "topics": {}}

    with open(baselines_file, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_metrics(events: list[dict], baselines: dict, date_str: str) -> dict:
    """
    計算每日指標

    Args:
        events: 事件列表
        baselines: 歷史基準線
        date_str: 日期

    Returns:
        metrics dict
    """
    # 統計各公司
    company_stats = defaultdict(lambda: {"count": 0, "sentiment_sum": 0.0})
    for event in events:
        companies = event.get("entities", {}).get("companies", [])
        sentiment_score = event.get("sentiment", {}).get("score", 0.0)

        for company in companies:
            company_stats[company]["count"] += 1
            company_stats[company]["sentiment_sum"] += sentiment_score

    by_company = {}
    for company, stats in company_stats.items():
        count = stats["count"]
        avg_sentiment = stats["sentiment_sum"] / count if count > 0 else 0.0
        by_company[company] = {
            "count": count,
            "sentiment_avg": round(avg_sentiment, 2),
        }

    # 統計各主題
    topic_stats = defaultdict(lambda: {"count": 0, "sentiment_sum": 0.0})
    for event in events:
        topics = event.get("topics", [])
        sentiment_score = event.get("sentiment", {}).get("score", 0.0)

        for topic in topics:
            topic_stats[topic]["count"] += 1
            topic_stats[topic]["sentiment_sum"] += sentiment_score

    by_topic = {}
    for topic, stats in topic_stats.items():
        count = stats["count"]
        avg_sentiment = stats["sentiment_sum"] / count if count > 0 else 0.0
        by_topic[topic] = {
            "count": count,
            "sentiment_avg": round(avg_sentiment, 2),
        }

    # 統計供應鏈活動
    supply_chain = calculate_supply_chain_activity(events)

    return {
        "date": date_str,
        "total_events": len(events),
        "by_company": by_company,
        "by_topic": by_topic,
        "baselines_used": {
            "companies": baselines.get("companies", {}),
            "topics": baselines.get("topics", {}),
        },
        "supply_chain_activity": supply_chain,
    }


def calculate_supply_chain_activity(events: list[dict]) -> list[dict]:
    """
    計算供應鏈活動（公司間的共同提及）

    Returns:
        [
            {
                "from": "samsung",
                "to": "nvidia",
                "relation": "supplier",
                "co_mention_count": 8,
                "topics": ["hbm", "ai_server"]
            },
            ...
        ]
    """
    # 統計公司對的共同提及
    pair_stats = defaultdict(lambda: {"count": 0, "topics": set()})

    for event in events:
        companies = event.get("entities", {}).get("companies", [])
        customers = event.get("entities", {}).get("customers", [])
        suppliers = event.get("entities", {}).get("suppliers", [])
        topics = event.get("topics", [])

        # 對每個公司對統計
        for i, c1 in enumerate(companies):
            for c2 in companies[i + 1:]:
                key = tuple(sorted([c1, c2]))
                pair_stats[key]["count"] += 1
                pair_stats[key]["topics"].update(topics)

                # 判斷關係
                if c1 in customers or c2 in suppliers:
                    pair_stats[key]["relation"] = "supplier_customer"
                elif c1 in suppliers or c2 in customers:
                    pair_stats[key]["relation"] = "supplier_customer"

    # 轉換為列表
    activities = []
    for (c1, c2), stats in pair_stats.items():
        if stats["count"] >= 2:  # 至少 2 次共同提及才記錄
            activities.append({
                "from": c1,
                "to": c2,
                "relation": stats.get("relation", "co_mention"),
                "co_mention_count": stats["count"],
                "topics": list(stats["topics"]),
            })

    # 按共同提及次數排序
    activities.sort(key=lambda x: x["co_mention_count"], reverse=True)

    return activities[:10]  # 只保留前 10


def save_metrics(metrics: dict, output_file: Path) -> None:
    """儲存指標"""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="每日指標計算腳本")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="處理日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--events-dir",
        type=str,
        default="data/events",
        help="事件目錄",
    )
    parser.add_argument(
        "--baselines-dir",
        type=str,
        default="data/baselines",
        help="基準線目錄",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/metrics",
        help="輸出目錄",
    )

    args = parser.parse_args()

    events_dir = Path(args.events_dir)
    baselines_dir = Path(args.baselines_dir)
    output_dir = Path(args.output_dir)

    # 載入今日事件
    events_file = events_dir / f"{args.date}.jsonl"
    events = load_events(events_file)

    if not events:
        print(f"警告：{events_file} 沒有事件")

    # 載入歷史基準線
    baselines = load_baselines(baselines_dir)

    # 計算指標
    metrics = calculate_metrics(events, baselines, args.date)

    # 儲存
    output_file = output_dir / f"{args.date}.json"
    save_metrics(metrics, output_file)

    print(f"指標計算完成：{len(events)} 則事件，輸出至 {output_file}")


if __name__ == "__main__":
    main()
