#!/usr/bin/env python3
"""
Add llm_analysis and generated_by fields to daily and 7d report JSONs.
Generates summaries and signals/watchlist based on event data, topics, and companies.
No external API calls - all analysis logic is inline.

Config-driven: reads topic names from configs/topics.yml and company names
from configs/companies.yml. Industry label is extracted from CLAUDE.md.
"""

import argparse
import json
import os
import re
import sys

import yaml

from pathlib import Path

BASE = str(Path(__file__).parent.parent)

# ─── Config loading ───


def load_topics():
    """Load topic display names from configs/topics.yml.

    Returns dict: topic_id -> display_name
    """
    path = os.path.join(BASE, "configs", "topics.yml")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found, using empty topics")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    topics_raw = data.get("topics", {})
    result = {}
    if isinstance(topics_raw, dict):
        for tid, info in topics_raw.items():
            if isinstance(info, dict):
                result[tid] = info.get("display", tid)
            else:
                result[tid] = tid
    elif isinstance(topics_raw, list):
        for item in topics_raw:
            if isinstance(item, dict):
                tid = item.get("id", "")
                result[tid] = item.get("display", item.get("name", tid))
    return result


def load_companies():
    """Load company display names from configs/companies.yml.

    Returns dict: company_id -> display_name
    Uses aliases[0] if available, otherwise name.
    """
    path = os.path.join(BASE, "configs", "companies.yml")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found, using empty companies")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    companies_raw = data.get("companies", [])
    result = {}
    for c in companies_raw:
        if not isinstance(c, dict):
            continue
        cid = c.get("id", "")
        aliases = c.get("aliases", [])
        name = c.get("name", cid)
        if aliases and isinstance(aliases, list) and len(aliases) > 0:
            result[cid] = aliases[0]
        else:
            result[cid] = name
    return result


def load_industry_label():
    """Extract industry label from CLAUDE.md first line.

    Expected format: # XX Intel - YY供應鏈情報追蹤
    Extracts the YY part (e.g., 鋼鐵, 汽車, 記憶體).
    Falls back to directory name if CLAUDE.md is missing.
    """
    claude_path = os.path.join(BASE, "CLAUDE.md")
    if os.path.exists(claude_path):
        with open(claude_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        # Try to extract: "# XX Intel - YY供應鏈情報追蹤" -> "YY產業"
        m = re.search(r"-\s*(.+?)供應鏈", first_line)
        if m:
            label = m.group(1).strip()
            # Avoid "回收產業" + "產業" -> "回收產業產業"
            if label.endswith("產業"):
                return label
            return label + "產業"
        # Try: "# XX Intel - YY產業情報追蹤" -> "YY產業"
        m = re.search(r"-\s*(.+?)產業", first_line)
        if m:
            return m.group(1).strip() + "產業"
        # Try: "# XX Intel - YY經濟" -> "YY經濟"
        m = re.search(r"-\s*(.+?)經濟", first_line)
        if m:
            return m.group(1).strip() + "經濟"
    # Fallback: use directory name
    dirname = os.path.basename(BASE).replace("-intel", "")
    return dirname + " 產業"


# ─── Globals loaded at startup ───
TOPIC_NAMES = load_topics()
COMPANY_NAMES = load_companies()
INDUSTRY_LABEL = load_industry_label()

# Identify "price/cost" and "shortage/supply" topic IDs for signal generation
PRICE_TOPIC_IDS = set()
SUPPLY_PRESSURE_TOPIC_IDS = set()
GROWTH_TOPIC_IDS = set()

for tid, display in TOPIC_NAMES.items():
    tid_lower = tid.lower()
    display_lower = display.lower() if display else ""
    if any(kw in tid_lower for kw in ("price", "cost", "pricing")):
        PRICE_TOPIC_IDS.add(tid)
    if any(kw in display_lower for kw in ("價格", "報價", "成本")):
        PRICE_TOPIC_IDS.add(tid)
    if any(kw in tid_lower for kw in ("shortage", "supply", "inventory", "scrap")):
        SUPPLY_PRESSURE_TOPIC_IDS.add(tid)
    if any(kw in display_lower for kw in ("缺貨", "庫存", "供應", "廢")):
        SUPPLY_PRESSURE_TOPIC_IDS.add(tid)
    if any(kw in tid_lower for kw in ("growth", "demand", "sales", "penetration", "ev_")):
        GROWTH_TOPIC_IDS.add(tid)
    if any(kw in display_lower for kw in ("成長", "需求", "銷量", "滲透")):
        GROWTH_TOPIC_IDS.add(tid)

# Combine price and supply pressure as "watch" topics
WATCH_TOPIC_IDS = PRICE_TOPIC_IDS | SUPPLY_PRESSURE_TOPIC_IDS


def read_events(date):
    """Read events from JSONL file. Returns list of event dicts."""
    path = os.path.join(BASE, "data", "events", f"{date}.jsonl")
    events = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def topic_name(t):
    return TOPIC_NAMES.get(t, t)


def company_name(c):
    return COMPANY_NAMES.get(c, c)


def generate_daily_analysis(date, daily_data, events):
    """Generate summary and signals for a daily report."""
    top_events = daily_data.get("top_events", [])
    stats = daily_data.get("stats", {})
    total = stats.get("total_events", 0)
    top_topics = stats.get("top_topics", [])
    top_companies = stats.get("top_companies", [])
    topic_trends = daily_data.get("topic_trends", {})
    anomalies = daily_data.get("anomalies", [])
    sentiment_dist = stats.get("sentiment_distribution", {})

    # ─── Build summary ───
    if total == 0:
        summary = f"{date} 無{INDUSTRY_LABEL}相關事件。市場處於平靜狀態，無重大訊號。"
    else:
        # First sentence: overview of what happened
        topic_strs = [topic_name(t["id"]) for t in top_topics[:3]]
        company_strs = [company_name(c["id"]) for c in top_companies[:3]]

        parts1 = []
        if company_strs:
            parts1.append("、".join(company_strs))
        if topic_strs:
            parts1.append("、".join(topic_strs))

        if top_events:
            top_title = top_events[0].get("title", "").strip()
            if len(top_title) > 60:
                top_title = top_title[:57] + "..."
            first_sentence = (
                f"今日共 {total} 則事件，焦點為"
                f"{parts1[0] if parts1 else INDUSTRY_LABEL}"
                f"相關動態：「{top_title}」。"
            )
        else:
            first_sentence = (
                f"今日共 {total} 則事件，涵蓋"
                f"{'、'.join(parts1) if parts1 else INDUSTRY_LABEL}"
                f"等領域。"
            )

        # Second sentence: sentiment or trend
        pos = sentiment_dist.get("positive", 0)
        neg = sentiment_dist.get("negative", 0)

        if neg > pos:
            second_sentence = "整體情緒偏負面，需留意潛在風險。"
        elif pos > neg:
            second_sentence = "整體情緒偏正面，市場信心回溫。"
        else:
            if topic_strs:
                second_sentence = f"主要關注主題為{'、'.join(topic_strs)}，市場情緒中性。"
            else:
                second_sentence = "市場情緒中性，暫無明顯方向。"

        summary = first_sentence + second_sentence

    # ─── Build signals ───
    signals = []

    # Signal from top event importance
    for ev in top_events[:2]:
        imp = ev.get("importance_score", 0)
        title = ev.get("title", "").strip()
        if len(title) > 80:
            title = title[:77] + "..."
        topics = ev.get("topics", [])

        if imp >= 0.9:
            level = "red"
        elif imp >= 0.7:
            level = "yellow"
        else:
            level = "green"

        topic_note = ""
        if topics:
            topic_note = f"（{'、'.join(topic_name(t) for t in topics)}）"

        signals.append({
            "text": f"{title}{topic_note}",
            "level": level,
        })

    # Signal from topic trends (config-driven)
    for t_id, trend_info in topic_trends.items():
        today_count = trend_info.get("today", 0)
        if today_count > 0 and t_id in WATCH_TOPIC_IDS:
            signals.append({
                "text": f"{topic_name(t_id)}話題出現 {today_count} 則，需持續關注供應鏈壓力。",
                "level": "yellow",
            })
        elif today_count > 0 and t_id in GROWTH_TOPIC_IDS:
            signals.append({
                "text": f"{topic_name(t_id)}持續受關注，產業趨勢帶動需求成長。",
                "level": "green",
            })

    # Ensure 2-3 signals
    if len(signals) == 0:
        signals.append({
            "text": "今日無重大異常訊號，產業動態平穩。",
            "level": "green",
        })
    if len(signals) == 1:
        if total > 0 and top_companies:
            signals.append({
                "text": (
                    f"{'、'.join(company_name(c['id']) for c in top_companies[:3])}"
                    f"為今日主要關注企業。"
                ),
                "level": "green",
            })
        else:
            signals.append({
                "text": "建議持續監控後續發展動態。",
                "level": "green",
            })

    # Cap at 3
    signals = signals[:3]

    return {
        "summary": summary,
        "signals": signals,
    }


def generate_7d_analysis(date, report_data, all_events_in_week):
    """Generate summary and watchlist for a 7d report."""
    highlights = report_data.get("highlights", [])
    topic_7d = report_data.get("topic_7d_summary", {})
    company_7d = report_data.get("company_7d_summary", {})
    comparisons = report_data.get("comparisons", {})
    date_range = report_data.get("date_range", {})
    start = date_range.get("start", "")
    end = date_range.get("end", date)
    daily_breakdown = report_data.get("daily_breakdown", [])

    total_events_week = sum(d.get("event_count", 0) for d in daily_breakdown)
    vs_last = comparisons.get("vs_last_week", {}).get("event_count", {})
    this_count = vs_last.get("this", total_events_week)
    last_count = vs_last.get("last", 0)
    change_pct = vs_last.get("change_pct", 0)

    # ─── Build summary ───
    if total_events_week == 0:
        summary = (
            f"本週（{start} ~ {end}）{INDUSTRY_LABEL}動態較為平靜，"
            f"未有重大事件發生。建議持續追蹤下週動態。"
        )
    else:
        # Identify key topics and companies this week
        active_topics = []
        for t_id, info in topic_7d.items():
            count = info.get("this_week", 0)
            if count > 0:
                active_topics.append(
                    (t_id, count, info.get("sentiment_this_week", 0))
                )

        active_topics.sort(key=lambda x: -x[1])

        active_companies = []
        for c_id, info in company_7d.items():
            count = info.get("event_count", 0)
            if count > 0:
                active_companies.append(
                    (c_id, count, info.get("sentiment_avg", 0))
                )

        active_companies.sort(key=lambda x: -x[1])

        # First sentence
        topic_strs = [topic_name(t[0]) for t in active_topics[:3]]
        company_strs = [company_name(c[0]) for c in active_companies[:3]]

        if highlights:
            top_highlight = highlights[0].get("title", "").strip()
            if len(top_highlight) > 50:
                top_highlight = top_highlight[:47] + "..."
            first = (
                f"本週（{start} ~ {end}）共 {this_count} 則事件，"
                f"重點為「{top_highlight}」。"
            )
        else:
            first = (
                f"本週（{start} ~ {end}）共 {this_count} 則事件，"
                f"主要涉及{'、'.join(topic_strs) if topic_strs else INDUSTRY_LABEL}。"
            )

        # Second sentence: comparison and sentiment
        if change_pct > 50 and last_count > 0:
            second = (
                f"事件量較上週增加 {change_pct:.0f}%，"
                f"產業動態明顯升溫，需密切關注。"
            )
        elif change_pct < -30 and last_count > 0:
            second = "事件量較上週減少，市場進入觀望階段。"
        else:
            neg_companies = [c for c in active_companies if c[2] < -0.2]
            pos_companies = [c for c in active_companies if c[2] > 0.2]
            if neg_companies:
                second = (
                    f"{'、'.join(company_name(c[0]) for c in neg_companies[:2])}"
                    f"情緒偏負面，建議留意相關風險。"
                )
            elif pos_companies:
                second = (
                    f"{'、'.join(company_name(c[0]) for c in pos_companies[:2])}"
                    f"表現正面，整體氣氛穩健。"
                )
            elif topic_strs:
                second = f"{'、'.join(topic_strs)}為本週焦點話題。"
            else:
                second = "產業動態穩定，無異常訊號。"

        summary = first + second

    # ─── Build watchlist ───
    watchlist = []

    # Companies with negative sentiment
    for c_id, info in company_7d.items():
        sent = info.get("sentiment_avg", 0)
        count = info.get("event_count", 0)
        name = company_name(c_id)
        if sent < -0.2:
            watchlist.append({
                "company": name,
                "reason": (
                    f"本週情緒偏負面（{sent:.1f}），"
                    f"共 {count} 則相關事件，需關注後續發展。"
                ),
            })

    # Companies with high event count
    for c_id, info in company_7d.items():
        sent = info.get("sentiment_avg", 0)
        count = info.get("event_count", 0)
        name = company_name(c_id)
        if count >= 3 and name not in [w["company"] for w in watchlist]:
            if sent >= 0:
                reason = (
                    f"本週出現 {count} 則相關事件，"
                    f"為高關注企業，動態頻繁。"
                )
            else:
                reason = (
                    f"本週出現 {count} 則相關事件且情緒偏負面，"
                    f"需特別關注。"
                )
            watchlist.append({
                "company": name,
                "reason": reason,
            })

    # Topics that indicate supply chain pressure (config-driven)
    for t_id, info in topic_7d.items():
        count = info.get("this_week", 0)
        if count > 0 and t_id in WATCH_TOPIC_IDS:
            related = []
            for h in highlights:
                title = h.get("title", "")
                for cid, cname in COMPANY_NAMES.items():
                    if (
                        cname.lower() in title.lower()
                        or cid in title.lower()
                    ):
                        if (
                            cname not in [w["company"] for w in watchlist]
                            and cname not in related
                        ):
                            related.append(cname)
            if related:
                for r in related[:1]:
                    watchlist.append({
                        "company": r,
                        "reason": (
                            f"受{topic_name(t_id)}議題影響，"
                            f"供應鏈壓力可能上升。"
                        ),
                    })
            elif not watchlist:
                for c_id2, info2 in company_7d.items():
                    name = company_name(c_id2)
                    if name not in [w["company"] for w in watchlist]:
                        watchlist.append({
                            "company": name,
                            "reason": (
                                f"{topic_name(t_id)}趨勢值得關注，"
                                f"可能影響供應鏈佈局。"
                            ),
                        })
                        break

    # If still empty, add top companies
    if not watchlist:
        for c_id, info in company_7d.items():
            name = company_name(c_id)
            count = info.get("event_count", 0)
            watchlist.append({
                "company": name,
                "reason": f"本週有 {count} 則相關事件，建議持續追蹤動態。",
            })
            if len(watchlist) >= 2:
                break

    # If completely empty (no companies at all)
    if not watchlist:
        watchlist.append({
            "company": INDUSTRY_LABEL,
            "reason": (
                "本週無特定企業異常，"
                "建議持續追蹤整體產業走勢。"
            ),
        })

    # Cap at 3
    watchlist = watchlist[:3]

    return {
        "summary": summary,
        "watchlist": watchlist,
    }


def process_daily(date, events):
    """Process a single daily report."""
    path = os.path.join(BASE, "site", "data", "reports", "daily", f"{date}.json")
    if not os.path.exists(path):
        print(f"  [SKIP] daily/{date}.json not found")
        return False

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    analysis = generate_daily_analysis(date, data, events)
    data["llm_analysis"] = analysis
    data["generated_by"] = "claude-cli"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  [OK] daily/{date}.json - summary: {analysis['summary'][:50]}...")
    return True


def process_7d(date, events):
    """Process a single 7d report."""
    path = os.path.join(BASE, "site", "data", "reports", "7d", f"{date}.json")
    if not os.path.exists(path):
        print(f"  [SKIP] 7d/{date}.json not found")
        return False

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    analysis = generate_7d_analysis(date, data, events)
    data["llm_analysis"] = analysis
    data["generated_by"] = "claude-cli"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"  [OK] 7d/{date}.json - summary: {analysis['summary'][:50]}...")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Generate LLM analysis for daily and 7d reports"
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Date to process (YYYY-MM-DD)",
    )
    args = parser.parse_args()
    date = args.date

    print("=" * 60)
    print(f"Generate LLM Analysis - {INDUSTRY_LABEL}")
    print(f"Base: {BASE}")
    print(f"Date: {date}")
    print(f"Topics: {len(TOPIC_NAMES)} loaded")
    print(f"Companies: {len(COMPANY_NAMES)} loaded")
    print(f"Watch topics: {', '.join(topic_name(t) for t in WATCH_TOPIC_IDS) or 'none'}")
    print("=" * 60)

    # Read events
    events = read_events(date)
    print(f"\nEvents: {len(events)} found for {date}")

    # Process daily report
    daily_ok = process_daily(date, events)

    # Process 7d report
    weekly_ok = process_7d(date, events)

    print(f"\n{'=' * 60}")
    status_parts = []
    if daily_ok:
        status_parts.append("daily")
    if weekly_ok:
        status_parts.append("7d")
    if status_parts:
        print(f"Done! Processed: {', '.join(status_parts)}")
    else:
        print("No reports found to process.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
