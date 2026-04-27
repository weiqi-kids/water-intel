#!/usr/bin/env python3
"""
7 日報告生成腳本

功能：
1. 讀取過去 7 天的事件和指標
2. 計算亮點（highlights）
3. 計算週趨勢
4. 輸出 reports/7d/{date}.json

每天重新生成，涵蓋「過去 7 天」而非傳統週報。

用法：
    python scripts/generate_7d_report.py --date 2026-03-14
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml


def load_events_for_date(events_dir: Path, date_str: str) -> list[dict]:
    """載入特定日期的事件"""
    events_file = events_dir / f"{date_str}.jsonl"
    if not events_file.exists():
        return []

    events = []
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    return events


def load_metrics_for_date(metrics_dir: Path, date_str: str) -> dict:
    """載入特定日期的指標"""
    metrics_file = metrics_dir / f"{date_str}.json"
    if not metrics_file.exists():
        return {}

    with open(metrics_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_7d_highlights_rules(config_dir: Path) -> dict:
    """載入亮點偵測規則"""
    rules_file = config_dir / "7d_highlights_rules.yml"
    if not rules_file.exists():
        return {}

    with open(rules_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_date_range(end_date: str, days: int) -> list[str]:
    """取得日期範圍"""
    end = datetime.fromisoformat(end_date)
    dates = []
    for i in range(days - 1, -1, -1):
        d = end - timedelta(days=i)
        dates.append(d.strftime("%Y-%m-%d"))
    return dates


def aggregate_7d_events(events_dir: Path, dates: list[str]) -> list[dict]:
    """彙整 7 天的事件"""
    all_events = []
    for date_str in dates:
        events = load_events_for_date(events_dir, date_str)
        all_events.extend(events)
    return all_events


def aggregate_7d_metrics(metrics_dir: Path, dates: list[str], events_dir: Path | None = None) -> dict:
    """
    彙整 7 天的指標

    Returns:
        {
            "by_company": {
                "samsung": {"total_count": 45, "sentiment_sum": 13.5},
                ...
            },
            "by_topic": {
                "hbm": {"total_count": 42, "sentiment_sum": 12.0},
                ...
            },
            "daily": [
                {"date": "2026-03-08", "event_count": 25, ...},
                ...
            ],
            "anomalies_all": [...],
        }
    """
    by_company = defaultdict(lambda: {"total_count": 0, "sentiment_sum": 0.0})
    by_topic = defaultdict(lambda: {"total_count": 0, "sentiment_sum": 0.0})
    daily = []
    anomalies_all = []

    for date_str in dates:
        metrics = load_metrics_for_date(metrics_dir, date_str)

        # 用 events 檔案的實際行數作為 event_count（metrics 是快照，可能過時）
        actual_count = 0
        if events_dir:
            events_file = events_dir / f"{date_str}.jsonl"
            if events_file.exists():
                actual_count = sum(1 for line in open(events_file, encoding="utf-8") if line.strip())

        if not metrics:
            daily.append({"date": date_str, "event_count": actual_count, "sentiment_avg": 0})
            continue

        # 日統計：優先用 events 檔案的實際行數
        total = actual_count if actual_count > 0 else metrics.get("total_events", 0)
        daily.append({
            "date": date_str,
            "event_count": total,
            "sentiment_avg": 0,  # 會再計算
        })

        # 公司統計
        for company_id, stats in metrics.get("by_company", {}).items():
            by_company[company_id]["total_count"] += stats["count"]
            by_company[company_id]["sentiment_sum"] += stats["sentiment_avg"] * stats["count"]

        # 主題統計
        for topic_id, stats in metrics.get("by_topic", {}).items():
            by_topic[topic_id]["total_count"] += stats["count"]
            by_topic[topic_id]["sentiment_sum"] += stats["sentiment_avg"] * stats["count"]

        # 異常
        anomalies_all.extend(metrics.get("anomalies", []))

    return {
        "by_company": dict(by_company),
        "by_topic": dict(by_topic),
        "daily": daily,
        "anomalies_all": anomalies_all,
    }


def find_top_event_7d(events: list[dict]) -> dict:
    """找出 7 天內最重要的事件"""
    if not events:
        return None

    best = max(events, key=lambda x: x.get("importance", {}).get("score", 0))

    return {
        "rank": 1,
        "type": "top_event",
        "event_id": best.get("id"),
        "date": best.get("date"),
        "title": best.get("title"),
        "importance_score": best.get("importance", {}).get("score", 0),
    }


def detect_sentiment_reversals(
    agg_metrics: dict,
    prev_week_metrics: dict,
) -> list[dict]:
    """
    偵測情緒大轉折

    Returns:
        情緒翻轉的公司/主題列表
    """
    reversals = []

    # 檢查公司
    for company_id, stats in agg_metrics.get("by_company", {}).items():
        if stats["total_count"] < 5:
            continue

        this_week_sentiment = stats["sentiment_sum"] / stats["total_count"]
        prev_stats = prev_week_metrics.get("by_company", {}).get(company_id, {})

        if prev_stats.get("total_count", 0) < 3:
            continue

        last_week_sentiment = prev_stats["sentiment_sum"] / prev_stats["total_count"]
        delta = this_week_sentiment - last_week_sentiment

        # 符號翻轉且差距大於 0.4
        if this_week_sentiment * last_week_sentiment < 0 and abs(delta) >= 0.4:
            reversals.append({
                "type": "sentiment_reversal",
                "subject": company_id,
                "subject_type": "company",
                "this_week_sentiment": round(this_week_sentiment, 2),
                "last_week_sentiment": round(last_week_sentiment, 2),
                "delta": round(delta, 2),
            })

    # 檢查主題
    for topic_id, stats in agg_metrics.get("by_topic", {}).items():
        if stats["total_count"] < 5:
            continue

        this_week_sentiment = stats["sentiment_sum"] / stats["total_count"]
        prev_stats = prev_week_metrics.get("by_topic", {}).get(topic_id, {})

        if prev_stats.get("total_count", 0) < 3:
            continue

        last_week_sentiment = prev_stats["sentiment_sum"] / prev_stats["total_count"]
        delta = this_week_sentiment - last_week_sentiment

        if this_week_sentiment * last_week_sentiment < 0 and abs(delta) >= 0.4:
            reversals.append({
                "type": "sentiment_reversal",
                "subject": topic_id,
                "subject_type": "topic",
                "this_week_sentiment": round(this_week_sentiment, 2),
                "last_week_sentiment": round(last_week_sentiment, 2),
                "delta": round(delta, 2),
            })

    return reversals


def detect_emerging_relations(
    events: list[dict],
    prev_week_events: list[dict],
) -> list[dict]:
    """偵測新出現的供應鏈關係"""
    # 統計本週的公司對共同提及
    this_week_pairs = defaultdict(int)
    for event in events:
        companies = event.get("entities", {}).get("companies", [])
        for i, c1 in enumerate(companies):
            for c2 in companies[i + 1:]:
                key = tuple(sorted([c1, c2]))
                this_week_pairs[key] += 1

    # 統計上週的公司對共同提及
    last_week_pairs = set()
    for event in prev_week_events:
        companies = event.get("entities", {}).get("companies", [])
        for i, c1 in enumerate(companies):
            for c2 in companies[i + 1:]:
                key = tuple(sorted([c1, c2]))
                last_week_pairs.add(key)

    # 找出新出現的關係（本週有、上週沒有）
    emerging = []
    for pair, count in this_week_pairs.items():
        if pair not in last_week_pairs and count >= 3:
            emerging.append({
                "type": "emerging_relation",
                "company_a": pair[0],
                "company_b": pair[1],
                "co_mention_count": count,
            })

    return sorted(emerging, key=lambda x: x["co_mention_count"], reverse=True)[:5]


def calculate_company_7d_summary(agg_metrics: dict) -> dict:
    """計算公司 7 日摘要"""
    summaries = {}

    for company_id, stats in agg_metrics.get("by_company", {}).items():
        count = stats["total_count"]
        sentiment_avg = stats["sentiment_sum"] / count if count > 0 else 0

        summaries[company_id] = {
            "event_count": count,
            "sentiment_avg": round(sentiment_avg, 2),
        }

    # 排名
    ranked = sorted(summaries.items(), key=lambda x: x[1]["event_count"], reverse=True)
    for rank, (company_id, _) in enumerate(ranked, 1):
        summaries[company_id]["rank"] = rank

    return summaries


def calculate_topic_7d_summary(
    agg_metrics: dict,
    prev_week_metrics: dict,
) -> dict:
    """計算主題 7 日摘要"""
    summaries = {}

    for topic_id, stats in agg_metrics.get("by_topic", {}).items():
        count = stats["total_count"]
        sentiment_avg = stats["sentiment_sum"] / count if count > 0 else 0

        prev_stats = prev_week_metrics.get("by_topic", {}).get(topic_id, {})
        prev_count = prev_stats.get("total_count", 0)

        # 計算週變化
        if prev_count > 0:
            wow_change = ((count - prev_count) / prev_count) * 100
        else:
            wow_change = None

        summaries[topic_id] = {
            "this_week": count,
            "last_week": prev_count,
            "week_over_week_change": f"+{wow_change:.0f}%" if wow_change and wow_change > 0 else f"{wow_change:.0f}%" if wow_change else "N/A",
            "sentiment_this_week": round(sentiment_avg, 2),
        }

    return summaries


def generate_7d_report(
    events_dir: Path,
    metrics_dir: Path,
    config_dir: Path,
    end_date: str,
) -> dict:
    """
    生成 7 日報告

    Args:
        events_dir: 事件目錄
        metrics_dir: 指標目錄
        config_dir: 設定檔目錄
        end_date: 結束日期

    Returns:
        7d report dict
    """
    # 取得日期範圍
    dates_7d = get_date_range(end_date, 7)
    start_date = dates_7d[0]

    # 上週日期範圍（用於比較）
    prev_end = (datetime.fromisoformat(start_date) - timedelta(days=1)).strftime("%Y-%m-%d")
    dates_prev_7d = get_date_range(prev_end, 7)

    # 彙整本週資料
    events_7d = aggregate_7d_events(events_dir, dates_7d)
    metrics_7d = aggregate_7d_metrics(metrics_dir, dates_7d, events_dir=events_dir)

    # 彙整上週資料
    events_prev_7d = aggregate_7d_events(events_dir, dates_prev_7d)
    metrics_prev_7d = aggregate_7d_metrics(metrics_dir, dates_prev_7d, events_dir=events_dir)

    # 計算亮點
    highlights = []

    # 本週最重要事件
    top_event = find_top_event_7d(events_7d)
    if top_event:
        highlights.append(top_event)

    # 情緒翻轉
    reversals = detect_sentiment_reversals(metrics_7d, metrics_prev_7d)
    for rev in reversals[:2]:
        rev["rank"] = len(highlights) + 1
        highlights.append(rev)

    # 新出現的關係
    emerging = detect_emerging_relations(events_7d, events_prev_7d)
    for em in emerging[:2]:
        em["rank"] = len(highlights) + 1
        highlights.append(em)

    # 摘要
    company_summary = calculate_company_7d_summary(metrics_7d)
    topic_summary = calculate_topic_7d_summary(metrics_7d, metrics_prev_7d)

    # 比較
    total_this_week = sum(d["event_count"] for d in metrics_7d["daily"])
    total_last_week = sum(d["event_count"] for d in metrics_prev_7d["daily"])

    comparisons = {
        "vs_last_week": {
            "event_count": {
                "this": total_this_week,
                "last": total_last_week,
                "change_pct": round(((total_this_week - total_last_week) / total_last_week * 100) if total_last_week > 0 else 0, 1),
            },
        },
    }

    return {
        "date": end_date,
        "date_range": {"start": start_date, "end": end_date},
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "highlights": highlights,
        "anomalies_7d": metrics_7d.get("anomalies_all", [])[:10],
        "topic_7d_summary": topic_summary,
        "company_7d_summary": company_summary,
        "comparisons": comparisons,
        "daily_breakdown": metrics_7d["daily"],
    }


def save_report(report: dict, output_file: Path) -> None:
    """儲存報告"""
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="7 日報告生成腳本")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="報告結束日期 (YYYY-MM-DD)",
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
        "--config-dir",
        type=str,
        default="configs",
        help="設定檔目錄",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/7d",
        help="輸出目錄",
    )

    args = parser.parse_args()

    events_dir = Path(args.events_dir)
    metrics_dir = Path(args.metrics_dir)
    config_dir = Path(args.config_dir)
    output_dir = Path(args.output_dir)

    # 生成報告
    report = generate_7d_report(events_dir, metrics_dir, config_dir, args.date)

    # 儲存
    output_file = output_dir / f"{args.date}.json"
    save_report(report, output_file)

    print(f"7 日報告生成完成：{report['date_range']['start']} ~ {report['date_range']['end']}")
    print(f"  亮點數：{len(report['highlights'])}")
    print(f"  輸出至 {output_file}")


if __name__ == "__main__":
    main()
