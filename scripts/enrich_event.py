#!/usr/bin/env python3
"""
事件標註腳本

功能：
1. 讀取原始新聞
2. 標註 entities（公司、客戶、供應商）
3. 標註 topics
4. 計算 sentiment
5. 計算 importance
6. 輸出到 data/events/{date}.jsonl

重複新聞處理：
- 同標題視為同一則新聞
- 合併 sources 陣列

用法：
    python scripts/enrich_event.py --date 2026-03-14
    python scripts/enrich_event.py --input raw_news.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 加入 lib 路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.matcher import load_matcher
from lib.sentiment import load_sentiment_analyzer
from lib.scorer import load_importance_scorer


def get_time_tags(date_str: str) -> dict:
    """
    從日期字串產生 time_tags

    Args:
        date_str: YYYY-MM-DD 格式

    Returns:
        time_tags dict
    """
    dt = datetime.fromisoformat(date_str)

    # 計算週數
    week_number = dt.isocalendar()[1]

    # 計算季度
    quarter = f"Q{(dt.month - 1) // 3 + 1}"

    # 星期幾
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday = weekdays[dt.weekday()]

    return {
        "year": dt.year,
        "quarter": quarter,
        "month": dt.month,
        "week": week_number,
        "weekday": weekday,
    }


def generate_event_id(company_id: str, date_str: str, seq: int) -> str:
    """產生事件 ID"""
    return f"{company_id}-{date_str}-{seq:03d}"


def load_today_events(events_file: Path) -> list[dict]:
    """載入今日已有的事件"""
    if not events_file.exists():
        return []

    events = []
    with open(events_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    return events


def save_events(events: list[dict], events_file: Path) -> None:
    """儲存事件（JSONL 格式）"""
    events_file.parent.mkdir(parents=True, exist_ok=True)

    with open(events_file, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")


def get_event_date(raw_event: dict, fallback_date: str) -> str:
    """
    從原始事件取得日期

    優先使用 published_at，否則使用 fallback_date

    Args:
        raw_event: 原始事件
        fallback_date: 備用日期（YYYY-MM-DD）

    Returns:
        日期字串（YYYY-MM-DD）
    """
    from email.utils import parsedate_to_datetime

    published_at = raw_event.get("published_at")
    if published_at:
        try:
            # 檢測 ISO 格式 "2026-03-10" 或 "2026-03-10T00:00:00"
            # ISO 格式特徵：第5個字元是 "-"（如 "2026-"）
            if len(published_at) >= 10 and published_at[4] == "-" and published_at[7] == "-":
                return published_at[:10]
            # 嘗試 RFC 2822 格式 "Sat, 14 Mar 2026 17:16:00 +0000"
            dt = parsedate_to_datetime(published_at)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass
    return fallback_date


def enrich_event(
    raw_event: dict,
    matcher,
    sentiment_analyzer,
    scorer,
    fallback_date: str,
    seq: int,
) -> dict:
    """
    標註單一事件

    Args:
        raw_event: 原始事件（需有 title, content, sources）
        matcher: KeywordMatcher
        sentiment_analyzer: SentimentAnalyzer
        scorer: ImportanceScorer
        fallback_date: 備用日期（當 published_at 不存在時使用）
        seq: 序號

    Returns:
        標註後的事件
    """
    title = raw_event.get("title", "")
    content = raw_event.get("content", "") or raw_event.get("summary", "")
    full_text = f"{title} {content}"

    # 取得事件日期（優先使用 published_at）
    date_str = get_event_date(raw_event, fallback_date)

    # 匹配 entities
    entities = matcher.build_entities(full_text)

    # 主要公司（用於 ID）
    primary_company = entities["companies"][0] if entities["companies"] else "unknown"

    # 匹配 topics
    topics = matcher.match_topics(full_text)

    # 計算 sentiment
    sentiment = sentiment_analyzer.analyze(full_text)

    # 建立初步事件結構（用於評分）
    partial_event = {
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment,
    }

    # 計算 importance
    importance = scorer.score(partial_event)

    # 建立完整事件
    event = {
        "id": generate_event_id(primary_company, date_str, seq),
        "date": date_str,
        "time_tags": get_time_tags(date_str),
        "entities": entities,
        "topics": topics,
        "sentiment": sentiment,
        "importance": importance,
        "title": title,
        "content": content,
        "sources": raw_event.get("sources") or (
            [{"name": raw_event["source"], "url": raw_event.get("url", ""), "type": "rss"}]
            if raw_event.get("source")
            else []
        ),
    }

    return event


def merge_event_sources(existing_event: dict, new_event: dict) -> dict:
    """
    合併重複事件的 sources

    Args:
        existing_event: 已存在的事件
        new_event: 新事件

    Returns:
        合併後的事件
    """
    existing_urls = {s["url"] for s in existing_event.get("sources", [])}

    for source in new_event.get("sources", []):
        if source["url"] not in existing_urls:
            existing_event["sources"].append(source)
            existing_urls.add(source["url"])

    return existing_event


def process_events(
    raw_events: list[dict],
    fallback_date: str,
    output_dir: Path,
    matcher,
    sentiment_analyzer,
    scorer,
) -> dict:
    """
    處理所有原始事件，按日期分組輸出

    Args:
        raw_events: 原始事件列表
        fallback_date: 備用日期（當 published_at 不存在時使用）
        output_dir: 輸出目錄
        matcher: KeywordMatcher
        sentiment_analyzer: SentimentAnalyzer
        scorer: ImportanceScorer

    Returns:
        dict: 每個日期新增的事件數 {date: count}
    """
    from collections import defaultdict

    # 按日期分組的事件
    events_by_date: dict[str, list[dict]] = defaultdict(list)

    # 載入所有現有事件（用於去重）
    all_existing_titles = set()
    for jsonl_file in output_dir.glob("*.jsonl"):
        for event in load_today_events(jsonl_file):
            all_existing_titles.add(event["title"])

    # 每個日期的序號計數器
    seq_by_date: dict[str, int] = defaultdict(int)
    for jsonl_file in output_dir.glob("*.jsonl"):
        date = jsonl_file.stem
        seq_by_date[date] = len(list(load_today_events(jsonl_file)))

    new_counts: dict[str, int] = defaultdict(int)

    # 過濾統計（供審計用）
    filter_stats = {
        "total_raw": len(raw_events),
        "dup_title": 0,
        "no_date": 0,
        "too_old": 0,
        "gate1_fail": 0,
        "gate2_fail": 0,
        "passed": 0,
        "gate2_samples": [],
    }

    for raw_event in raw_events:
        title = raw_event.get("title", "")

        if title in all_existing_titles:
            filter_stats["dup_title"] += 1
            continue

        # 過濾掉沒有 published_at 的事件（通常是抓錯的靜態頁面）
        if not raw_event.get("published_at"):
            filter_stats["no_date"] += 1
            continue

        # 過濾掉超過 7 天前的事件（避免 RSS 回傳歷史資料）
        event_date_str = get_event_date(raw_event, fallback_date)
        try:
            event_dt = datetime.fromisoformat(event_date_str)
            fallback_dt = datetime.fromisoformat(fallback_date)
            if (fallback_dt - event_dt).days > 7:
                filter_stats["too_old"] += 1
                continue
        except (ValueError, TypeError):
            pass

        # 預先檢查相關性
        title = raw_event.get("title", "")
        content = raw_event.get("content", "") or raw_event.get("summary", "")
        preview_text = f"{title} {content}"
        preview_companies = matcher.match_companies(preview_text)
        preview_topics = matcher.match_topics(preview_text)
        # 第一關：必須匹配到追蹤公司或追蹤主題
        if not preview_companies and not preview_topics:
            filter_stats["gate1_fail"] += 1
            continue
        # 第二關：標題或內容必須包含產業關鍵字（從 topics.yml 動態載入）
        # 加上通用商業關鍵字和通用財務關鍵字
        if not hasattr(process_events, '_industry_kw'):
            import yaml as _yaml
            _kws = set()
            _topics_file = Path(__file__).parent.parent / "configs" / "topics.yml"
            if _topics_file.exists():
                with open(_topics_file) as _f:
                    _tc = _yaml.safe_load(_f)
                for _t in (_tc.get("topics") or {}).values():
                    for _k in (_t.get("keywords") or []):
                        _kws.add(_k.lower())
            # 通用財務關鍵字
            _kws.update(["earnings", "revenue", "profit", "guidance", "forecast",
                         "quarterly results", "financial results",
                         "營收", "獲利", "財報", "法說"])
            # 通用商業關鍵字
            _kws.update([
                "acquisition", "merger", "partnership", "joint venture", "jv",
                "alliance", "supply chain", "supply agreement", "deal", "contract",
                "mou", "expansion", "investment", "plant", "factory", "production",
                "capacity", "market share", "shipment", "order", "backlog", "demand",
                "recall", "lawsuit", "regulatory", "tariff", "trade", "sanction", "ban",
                "ceo", "executive", "restructuring", "layoff", "hire",
                "r&d", "patent", "technology", "launch", "announce", "unveil",
                "ipo", "stake", "buyback", "dividend",
                "併購", "合資", "供應鏈", "擴產", "投資", "工廠", "產能",
                "出貨", "訂單", "需求", "關稅", "貿易", "裁員", "重組", "專利",
            ])
            process_events._industry_kw = _kws
        title_lower = (title + " " + content[:200]).lower()
        if process_events._industry_kw and not any(kw in title_lower for kw in process_events._industry_kw):
            filter_stats["gate2_fail"] += 1
            if len(filter_stats["gate2_samples"]) < 5:
                filter_stats["gate2_samples"].append(title[:100])
            continue

        filter_stats["passed"] += 1

        # 標註事件（使用實際事件日期做 seq 計數，避免跨日期 ID 衝突）
        actual_date = get_event_date(raw_event, fallback_date)
        seq_by_date[actual_date] += 1
        enriched = enrich_event(
            raw_event, matcher, sentiment_analyzer, scorer,
            fallback_date, seq_by_date[actual_date]
        )

        # 按事件的實際日期分組
        event_date = enriched["date"]
        events_by_date[event_date].append(enriched)
        all_existing_titles.add(title)
        new_counts[event_date] += 1

    # 儲存到各自的檔案
    for date, events in events_by_date.items():
        events_file = output_dir / f"{date}.jsonl"
        existing = load_today_events(events_file)
        existing.extend(events)
        save_events(existing, events_file)

    # 儲存過濾統計（供 generate_daily.py 讀取）— 累加模式，不覆蓋
    stats_dir = output_dir.parent / "metrics"
    stats_dir.mkdir(parents=True, exist_ok=True)
    stats_file = stats_dir / f"{fallback_date}_filter.json"
    if stats_file.exists():
        with open(stats_file, "r", encoding="utf-8") as f:
            prev = json.load(f)
        filter_stats["total_raw"] += prev.get("total_raw", 0)
        filter_stats["dup_title"] += prev.get("dup_title", 0)
        filter_stats["no_date"] += prev.get("no_date", 0)
        filter_stats["too_old"] += prev.get("too_old", 0)
        filter_stats["gate1_fail"] += prev.get("gate1_fail", 0)
        filter_stats["gate2_fail"] += prev.get("gate2_fail", 0)
        filter_stats["passed"] += prev.get("passed", 0)
        prev_samples = prev.get("gate2_samples", [])
        combined = prev_samples + filter_stats["gate2_samples"]
        filter_stats["gate2_samples"] = combined[:5]
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(filter_stats, f, ensure_ascii=False, indent=2)

    if filter_stats["no_date"] > 0:
        print(f"（跳過 {filter_stats['no_date']} 則無日期事件）")

    return dict(new_counts)


def main():
    parser = argparse.ArgumentParser(description="事件標註腳本")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="處理日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--input",
        type=str,
        help="輸入的原始新聞 JSON 檔案",
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
        default="data/events",
        help="輸出目錄",
    )

    args = parser.parse_args()

    # 載入設定
    config_dir = Path(args.config_dir)
    matcher = load_matcher(
        topics_path=str(config_dir / "topics.yml"),
        companies_path=str(config_dir / "companies.yml"),
    )
    sentiment_analyzer = load_sentiment_analyzer(
        rules_path=str(config_dir / "sentiment_rules.yml"),
    )
    scorer = load_importance_scorer(
        rules_path=str(config_dir / "importance_rules.yml"),
        matcher=matcher,
    )

    # 載入原始新聞
    if args.input:
        input_path = Path(args.input)
        if input_path.suffix == ".jsonl":
            # JSONL 格式
            raw_events = []
            with open(input_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        raw_events.append(json.loads(line))
        else:
            # JSON 格式
            with open(args.input, "r", encoding="utf-8") as f:
                raw_events = json.load(f)
    else:
        # 從 stdin 讀取
        raw_events = json.load(sys.stdin)

    # 處理（按日期分組輸出）
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    new_counts = process_events(
        raw_events,
        args.date,
        output_dir,
        matcher,
        sentiment_analyzer,
        scorer,
    )

    total = sum(new_counts.values())
    print(f"處理完成：新增 {total} 則事件")
    for date, count in sorted(new_counts.items()):
        print(f"  {date}: {count} 則")


if __name__ == "__main__":
    main()
