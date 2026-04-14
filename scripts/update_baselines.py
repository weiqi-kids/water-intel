#!/usr/bin/env python3
"""
更新歷史基準線腳本

功能：
1. 讀取今日指標
2. 更新滾動平均值（7d, 30d）
3. 更新去年同期資料
4. 更新主題最後出現日期
5. 輸出 data/baselines/baselines.json

重要：此腳本應在生成報告之後執行，避免今日資料影響今日報告的基準線比較。

用法：
    python scripts/update_baselines.py --date 2026-03-14
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def load_metrics_for_date(metrics_dir: Path, date_str: str) -> dict:
    """載入特定日期的指標"""
    metrics_file = metrics_dir / f"{date_str}.json"
    if not metrics_file.exists():
        return {}

    with open(metrics_file, "r", encoding="utf-8") as f:
        return json.load(f)


def load_baselines(baselines_dir: Path) -> dict:
    """載入現有基準線"""
    baselines_file = baselines_dir / "baselines.json"
    if not baselines_file.exists():
        return {
            "companies": {},
            "topics": {},
            "history": {
                "companies": defaultdict(list),  # company_id -> [(date, count, sentiment), ...]
                "topics": defaultdict(list),
            },
            "last_updated": None,
        }

    with open(baselines_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 確保 history 結構存在
    if "history" not in data:
        data["history"] = {
            "companies": defaultdict(list),
            "topics": defaultdict(list),
        }

    return data


def save_baselines(baselines: dict, baselines_dir: Path) -> None:
    """儲存基準線"""
    baselines_dir.mkdir(parents=True, exist_ok=True)
    baselines_file = baselines_dir / "baselines.json"

    with open(baselines_file, "w", encoding="utf-8") as f:
        json.dump(baselines, f, ensure_ascii=False, indent=2)


def calculate_rolling_avg(
    history: list,
    days: int,
    date_str: str,
) -> tuple[float, float]:
    """
    計算滾動平均

    Args:
        history: [(date, count, sentiment), ...] 按日期排序
        days: 滾動天數
        date_str: 今天日期

    Returns:
        (count_avg, sentiment_avg)
    """
    today = datetime.fromisoformat(date_str)
    start_date = today - timedelta(days=days)

    relevant = [
        (count, sentiment)
        for date, count, sentiment in history
        if start_date <= datetime.fromisoformat(date) < today
    ]

    if not relevant:
        return None, None

    count_sum = sum(c for c, _ in relevant)
    sentiment_sum = sum(s * c for c, s in relevant)
    total_count = sum(c for c, _ in relevant)

    count_avg = count_sum / len(relevant) if relevant else 0
    sentiment_avg = sentiment_sum / total_count if total_count > 0 else 0

    return round(count_avg, 2), round(sentiment_avg, 2)


def get_yoy_same_week(
    history: list,
    date_str: str,
) -> int:
    """
    取得去年同週的數量

    Args:
        history: [(date, count, sentiment), ...]
        date_str: 今天日期

    Returns:
        去年同週的事件數，或 None
    """
    today = datetime.fromisoformat(date_str)
    this_week = today.isocalendar()[1]
    last_year = today.year - 1

    # 找去年同週的資料
    for date, count, sentiment in history:
        dt = datetime.fromisoformat(date)
        if dt.year == last_year and dt.isocalendar()[1] == this_week:
            return count

    return None


def update_baselines(
    metrics: dict,
    baselines: dict,
    date_str: str,
    max_history_days: int = 400,
) -> dict:
    """
    更新基準線

    Args:
        metrics: 今日指標
        baselines: 現有基準線
        date_str: 今日日期
        max_history_days: 保留多少天的歷史

    Returns:
        更新後的基準線
    """
    today = datetime.fromisoformat(date_str)
    cutoff = today - timedelta(days=max_history_days)

    # 更新公司歷史
    company_history = baselines.get("history", {}).get("companies", {})
    for company_id, stats in metrics.get("by_company", {}).items():
        if company_id not in company_history:
            company_history[company_id] = []

        # 加入今日資料
        company_history[company_id].append(
            (date_str, stats["count"], stats["sentiment_avg"])
        )

        # 清理過舊的資料
        company_history[company_id] = [
            (d, c, s) for d, c, s in company_history[company_id]
            if datetime.fromisoformat(d) >= cutoff
        ]

    # 更新主題歷史
    topic_history = baselines.get("history", {}).get("topics", {})
    for topic_id, stats in metrics.get("by_topic", {}).items():
        if topic_id not in topic_history:
            topic_history[topic_id] = []

        topic_history[topic_id].append(
            (date_str, stats["count"], stats["sentiment_avg"])
        )

        topic_history[topic_id] = [
            (d, c, s) for d, c, s in topic_history[topic_id]
            if datetime.fromisoformat(d) >= cutoff
        ]

    # 計算公司基準線
    company_baselines = {}
    for company_id, history in company_history.items():
        avg_7d, sentiment_7d = calculate_rolling_avg(history, 7, date_str)
        avg_30d, sentiment_30d = calculate_rolling_avg(history, 30, date_str)
        yoy = get_yoy_same_week(history, date_str)

        company_baselines[company_id] = {
            "7d_avg": avg_7d,
            "30d_avg": avg_30d,
            "yoy_same_week": yoy,
            "sentiment_7d_avg": sentiment_7d,
            "sentiment_30d_avg": sentiment_30d,
            "data_days": len(history),
        }

    # 計算主題基準線
    topic_baselines = {}
    for topic_id, history in topic_history.items():
        avg_7d, sentiment_7d = calculate_rolling_avg(history, 7, date_str)
        avg_30d, sentiment_30d = calculate_rolling_avg(history, 30, date_str)
        yoy = get_yoy_same_week(history, date_str)

        # 找最後出現日期
        last_seen = None
        for d, c, s in sorted(history, reverse=True):
            if c > 0 and d != date_str:
                last_seen = d
                break

        topic_baselines[topic_id] = {
            "7d_avg": avg_7d,
            "30d_avg": avg_30d,
            "yoy_same_week": yoy,
            "sentiment_7d_avg": sentiment_7d,
            "sentiment_30d_avg": sentiment_30d,
            "last_seen": last_seen,
            "data_days": len(history),
        }

    return {
        "companies": company_baselines,
        "topics": topic_baselines,
        "history": {
            "companies": company_history,
            "topics": topic_history,
        },
        "last_updated": date_str,
    }


def main():
    parser = argparse.ArgumentParser(description="更新歷史基準線腳本")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="處理日期 (YYYY-MM-DD)",
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
        "--max-history",
        type=int,
        default=400,
        help="保留多少天的歷史",
    )

    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    baselines_dir = Path(args.baselines_dir)

    # 載入今日指標
    metrics = load_metrics_for_date(metrics_dir, args.date)
    if not metrics:
        print(f"警告：找不到 {args.date} 的指標")
        return

    # 載入現有基準線
    baselines = load_baselines(baselines_dir)

    # 更新
    new_baselines = update_baselines(
        metrics,
        baselines,
        args.date,
        args.max_history,
    )

    # 儲存
    save_baselines(new_baselines, baselines_dir)

    print(f"基準線更新完成：")
    print(f"  公司數：{len(new_baselines['companies'])}")
    print(f"  主題數：{len(new_baselines['topics'])}")
    print(f"  更新日期：{args.date}")


if __name__ == "__main__":
    main()
