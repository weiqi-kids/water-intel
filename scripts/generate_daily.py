#!/usr/bin/env python3
"""
每日報告生成腳本

功能：
1. 讀取今日事件和指標
2. 選出 Top 5 重要新聞
3. 整理異常
4. 計算主題趨勢
5. 輸出 reports/daily/{date}.json

用法：
    python scripts/generate_daily.py --date 2026-03-14
"""

import argparse
import json
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


def load_metrics(metrics_file: Path) -> dict:
    """載入指標"""
    if not metrics_file.exists():
        return {}

    with open(metrics_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_baselines(baselines_dir: Path) -> dict:
    """載入歷史基準線"""
    baselines_file = baselines_dir / "baselines.json"
    if not baselines_file.exists():
        return {"companies": {}, "topics": {}}

    with open(baselines_file, "r", encoding="utf-8") as f:
        return json.load(f)


def get_top_events(events: list[dict], limit: int = 5) -> list[dict]:
    """
    取得最重要的事件

    Args:
        events: 事件列表
        limit: 取幾則

    Returns:
        Top N 事件（簡化版）
    """
    # 按重要性排序
    sorted_events = sorted(
        events,
        key=lambda x: x.get("importance", {}).get("score", 0),
        reverse=True,
    )

    top_events = []
    for i, event in enumerate(sorted_events[:limit]):
        importance = event.get("importance", {})
        entities = event.get("entities", {})
        sentiment = event.get("sentiment", {})

        top_events.append({
            "rank": i + 1,
            "event_id": event.get("id"),
            "importance_score": importance.get("score", 0),
            "importance_reasons": importance.get("reasons", []),
            "title": event.get("title"),
            "companies": entities.get("companies", []),
            "related": {
                "customers": entities.get("customers", []),
                "suppliers": entities.get("suppliers", []),
            },
            "topics": event.get("topics", []),
            "sentiment": {
                "label": sentiment.get("label"),
                "score": sentiment.get("score"),
            },
            "source_url": event.get("sources", [{}])[0].get("url") if event.get("sources") else None,
        })

    return top_events


def calculate_topic_trends(
    metrics: dict,
    baselines: dict,
) -> dict:
    """
    計算主題趨勢

    Returns:
        {
            "hbm": {
                "today": 15,
                "7d_avg": 8,
                "30d_avg": 6,
                "yoy_same_week": 5,
                "trend": "rising" | "falling" | "stable",
                "sentiment_today": 0.5,
                "sentiment_7d_avg": 0.6,
            },
            ...
        }
    """
    by_topic = metrics.get("by_topic", {})
    baseline_topics = baselines.get("topics", {})

    trends = {}

    for topic_id, stats in by_topic.items():
        baseline = baseline_topics.get(topic_id, {})

        today_count = stats["count"]
        avg_7d = baseline.get("7d_avg") or 0
        avg_30d = baseline.get("30d_avg") or 0

        # 判斷趨勢
        if avg_7d > 0:
            if today_count > avg_7d * 1.2:
                trend = "rising"
            elif today_count < avg_7d * 0.8:
                trend = "falling"
            else:
                trend = "stable"
        else:
            trend = "new" if today_count > 0 else "stable"

        trends[topic_id] = {
            "today": today_count,
            "7d_avg": avg_7d,
            "30d_avg": avg_30d,
            "yoy_same_week": baseline.get("yoy_same_week"),
            "trend": trend,
            "consecutive_weeks_rising": baseline.get("consecutive_weeks_rising", 0),
            "sentiment_today": stats["sentiment_avg"],
            "sentiment_7d_avg": baseline.get("sentiment_7d_avg"),
        }

    return trends


def calculate_stats(events: list[dict], metrics: dict) -> dict:
    """計算統計資訊"""
    # 情緒分布
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    for event in events:
        label = event.get("sentiment", {}).get("label", "neutral")
        sentiment_dist[label] = sentiment_dist.get(label, 0) + 1

    # 公司排名
    by_company = metrics.get("by_company", {})
    top_companies = sorted(
        [{"id": k, "count": v["count"]} for k, v in by_company.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    # 主題排名
    by_topic = metrics.get("by_topic", {})
    top_topics = sorted(
        [{"id": k, "count": v["count"]} for k, v in by_topic.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:5]

    return {
        "total_events": len(events),
        "sentiment_distribution": sentiment_dist,
        "top_companies": top_companies,
        "top_topics": top_topics,
    }


def generate_daily_report(
    events: list[dict],
    metrics: dict,
    baselines: dict,
    date_str: str,
) -> dict:
    """
    生成每日報告

    Returns:
        daily report dict
    """
    top_events = get_top_events(events)
    anomalies = metrics.get("anomalies", [])
    topic_trends = calculate_topic_trends(metrics, baselines)
    supply_chain = metrics.get("supply_chain_activity", [])
    stats = calculate_stats(events, metrics)

    return {
        "date": date_str,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top_events": top_events,
        "anomalies": anomalies,
        "topic_trends": topic_trends,
        "supply_chain_activity": supply_chain,
        "stats": stats,
    }


def save_report(report: dict, output_file: Path) -> None:
    """儲存報告"""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="每日報告生成腳本")
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
        "--metrics-dir",
        type=str,
        default="data/metrics",
        help="指標目錄",
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
        default="reports/daily",
        help="輸出目錄",
    )

    args = parser.parse_args()

    events_dir = Path(args.events_dir)
    metrics_dir = Path(args.metrics_dir)
    baselines_dir = Path(args.baselines_dir)
    output_dir = Path(args.output_dir)

    # 載入資料
    events_file = events_dir / f"{args.date}.jsonl"
    metrics_file = metrics_dir / f"{args.date}.json"

    events = load_events(events_file)
    metrics = load_metrics(metrics_file)
    baselines = load_baselines(baselines_dir)

    if not events:
        print(f"警告：{events_file} 沒有事件")

    # 生成報告
    report = generate_daily_report(events, metrics, baselines, args.date)

    # 儲存
    output_file = output_dir / f"{args.date}.json"
    save_report(report, output_file)

    print(f"每日報告生成完成：{len(report['top_events'])} 則重要新聞，{len(report['anomalies'])} 個異常")
    print(f"輸出至 {output_file}")


if __name__ == "__main__":
    main()
