#!/usr/bin/env python3
"""
測試完整流程

將現有 site/data/events.json 轉換為新格式並執行完整流程。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 加入 lib 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.matcher import load_matcher
from lib.sentiment import load_sentiment_analyzer
from lib.scorer import load_importance_scorer


def convert_old_event(old_event: dict) -> dict:
    """將舊格式轉換為新的 raw 格式"""
    # 取得內容（合併 summary 和所有 sources 的 excerpt）
    content_parts = []

    if old_event.get("summary"):
        content_parts.append(old_event["summary"])

    for source in old_event.get("sources", []):
        excerpt = source.get("excerpt", "")
        if excerpt and excerpt not in content_parts:
            content_parts.append(excerpt)

    content = " ".join(content_parts)

    return {
        "title": old_event.get("title", ""),
        "content": content,
        "sources": old_event.get("sources", []),
    }


def get_time_tags(date_str: str) -> dict:
    """從日期字串產生 time_tags"""
    dt = datetime.fromisoformat(date_str)
    week_number = dt.isocalendar()[1]
    quarter = f"Q{(dt.month - 1) // 3 + 1}"
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = weekdays[dt.weekday()]

    return {
        "year": dt.year,
        "quarter": quarter,
        "month": dt.month,
        "week": week_number,
        "weekday": weekday,
    }


def enrich_event(raw_event: dict, matcher, sentiment_analyzer, scorer, date_str: str, seq: int) -> dict:
    """標註單一事件"""
    title = raw_event.get("title", "")
    content = raw_event.get("content", "")
    full_text = f"{title} {content}"

    # 匹配 entities
    entities = matcher.build_entities(full_text)

    # 主要公司
    primary_company = entities["companies"][0] if entities["companies"] else "unknown"

    # 匹配 topics
    topics = matcher.match_topics(full_text)

    # 計算 sentiment
    sentiment = sentiment_analyzer.analyze(full_text)

    # 建立初步事件結構
    partial_event = {
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment,
    }

    # 計算 importance
    importance = scorer.score(partial_event)

    return {
        "id": f"{primary_company}-{date_str}-{seq:03d}",
        "date": date_str,
        "time_tags": get_time_tags(date_str),
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment,
        "importance": importance,
        "title": title,
        "content": content,
        "sources": raw_event.get("sources", []),
    }


def main():
    base_dir = Path(__file__).parent.parent

    print("=" * 60)
    print("測試完整流程")
    print("=" * 60)

    # 載入設定
    print("\n1. 載入設定...")
    config_dir = base_dir / "configs"

    matcher = load_matcher(
        topics_path=str(config_dir / "topics.yml"),
        companies_path=str(config_dir / "companies.yml"),
    )
    print(f"   - 載入 {len(matcher.topics)} 個主題")
    print(f"   - 載入 {len(matcher.companies)} 家公司")

    sentiment_analyzer = load_sentiment_analyzer(
        rules_path=str(config_dir / "sentiment_rules.yml"),
    )
    print(f"   - 載入情緒分析器")

    scorer = load_importance_scorer(
        rules_path=str(config_dir / "importance_rules.yml"),
        matcher=matcher,
    )
    print(f"   - 載入重要性評分器")

    # 載入現有事件
    print("\n2. 載入現有事件...")
    old_events_file = base_dir / "site" / "data" / "events.json"
    with open(old_events_file, "r", encoding="utf-8") as f:
        old_events = json.load(f)
    print(f"   - 載入 {len(old_events)} 則事件")

    # 轉換並標註
    print("\n3. 轉換並標註事件...")
    enriched_events = []

    # 按日期分組
    events_by_date = {}
    for old_event in old_events:
        date = old_event.get("date")
        if date:
            if date not in events_by_date:
                events_by_date[date] = []
            events_by_date[date].append(old_event)

    for date_str in sorted(events_by_date.keys(), reverse=True):
        date_events = events_by_date[date_str]
        for seq, old_event in enumerate(date_events, 1):
            raw_event = convert_old_event(old_event)
            enriched = enrich_event(raw_event, matcher, sentiment_analyzer, scorer, date_str, seq)
            enriched_events.append(enriched)

    print(f"   - 標註完成：{len(enriched_events)} 則")

    # 顯示範例
    print("\n4. 標註範例（前 3 則）...")
    for event in enriched_events[:3]:
        print(f"\n   標題: {event['title'][:50]}...")
        print(f"   公司: {event['entities']['companies']}")
        print(f"   主題: {event['topics']}")
        print(f"   情緒: {event['sentiment']['label']} ({event['sentiment']['score']})")
        print(f"   重要性: {event['importance']['score']} - {event['importance']['reasons']}")

    # 儲存到 data/events/
    print("\n5. 儲存事件到 data/events/...")
    events_dir = base_dir / "data" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    # 按日期分檔存儲
    saved_dates = set()
    for event in enriched_events:
        date_str = event["date"]
        events_file = events_dir / f"{date_str}.jsonl"

        # 如果是新日期，清空檔案
        if date_str not in saved_dates:
            with open(events_file, "w", encoding="utf-8") as f:
                pass  # 清空
            saved_dates.add(date_str)

        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(f"   - 儲存 {len(saved_dates)} 個日期的事件")

    # 計算指標
    print("\n6. 計算指標...")
    from collections import defaultdict

    metrics_dir = base_dir / "data" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    for date_str in sorted(saved_dates, reverse=True)[:3]:  # 只處理最近 3 天
        # 載入當天事件
        events_file = events_dir / f"{date_str}.jsonl"
        day_events = []
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    day_events.append(json.loads(line))

        # 統計
        by_company = defaultdict(lambda: {"count": 0, "sentiment_sum": 0.0})
        by_topic = defaultdict(lambda: {"count": 0, "sentiment_sum": 0.0})

        for event in day_events:
            sentiment_score = event.get("sentiment", {}).get("score", 0.0)

            for company in event.get("entities", {}).get("companies", []):
                by_company[company]["count"] += 1
                by_company[company]["sentiment_sum"] += sentiment_score

            for topic in event.get("topics", []):
                by_topic[topic]["count"] += 1
                by_topic[topic]["sentiment_sum"] += sentiment_score

        # 計算平均
        for company, stats in by_company.items():
            if stats["count"] > 0:
                stats["sentiment_avg"] = round(stats["sentiment_sum"] / stats["count"], 2)
            del stats["sentiment_sum"]

        for topic, stats in by_topic.items():
            if stats["count"] > 0:
                stats["sentiment_avg"] = round(stats["sentiment_sum"] / stats["count"], 2)
            del stats["sentiment_sum"]

        metrics = {
            "date": date_str,
            "total_events": len(day_events),
            "by_company": dict(by_company),
            "by_topic": dict(by_topic),
            "anomalies": [],  # 目前沒有基準線，不偵測異常
        }

        metrics_file = metrics_dir / f"{date_str}.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2)

        print(f"   - {date_str}: {len(day_events)} 則事件, {len(by_company)} 家公司, {len(by_topic)} 個主題")

    # 生成每日報告
    print("\n7. 生成每日報告...")
    reports_dir = base_dir / "reports" / "daily"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for date_str in sorted(saved_dates, reverse=True)[:1]:  # 只處理最新一天
        # 載入事件
        events_file = events_dir / f"{date_str}.jsonl"
        day_events = []
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    day_events.append(json.loads(line))

        # 載入指標
        metrics_file = metrics_dir / f"{date_str}.json"
        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics = json.load(f)

        # Top 5 事件
        sorted_events = sorted(
            day_events,
            key=lambda x: x.get("importance", {}).get("score", 0),
            reverse=True,
        )

        top_events = []
        for i, event in enumerate(sorted_events[:5]):
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
                "topics": event.get("topics", []),
                "sentiment": {
                    "label": sentiment.get("label"),
                    "score": sentiment.get("score"),
                },
            })

        report = {
            "date": date_str,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "top_events": top_events,
            "anomalies": [],
            "stats": {
                "total_events": len(day_events),
            },
        }

        report_file = reports_dir / f"{date_str}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"   - {date_str}: 生成報告，Top 5 新聞")

        print("\n   Top 5 重要新聞:")
        for ev in top_events:
            print(f"   {ev['rank']}. [{ev['importance_score']:.2f}] {ev['title'][:50]}...")
            print(f"      主題: {ev['topics']}")
            print(f"      理由: {ev['importance_reasons']}")

    print("\n" + "=" * 60)
    print("測試完成！")
    print("=" * 60)
    print(f"\n輸出檔案:")
    print(f"  - data/events/*.jsonl")
    print(f"  - data/metrics/*.json")
    print(f"  - reports/daily/*.json")


if __name__ == "__main__":
    main()
