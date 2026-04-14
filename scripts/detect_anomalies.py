#!/usr/bin/env python3
"""
異常偵測腳本

功能：
1. 讀取今日指標
2. 與歷史基準線比較
3. 偵測異常（volume_spike, sentiment_shift, topic_resurface）
4. 更新 metrics 檔案，加入 anomalies

用法：
    python scripts/detect_anomalies.py --date 2026-03-14
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.anomaly import load_anomaly_detector


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


def detect_all_anomalies(
    metrics: dict,
    baselines: dict,
    detector,
    date_str: str,
) -> list[dict]:
    """
    偵測所有異常

    Args:
        metrics: 今日指標
        baselines: 歷史基準線
        detector: AnomalyDetector
        date_str: 今日日期

    Returns:
        異常列表
    """
    anomalies = []

    by_company = metrics.get("by_company", {})
    by_topic = metrics.get("by_topic", {})
    baseline_companies = baselines.get("companies", {})
    baseline_topics = baselines.get("topics", {})

    # 偵測公司新聞量異常
    for company_id, stats in by_company.items():
        company_baseline = baseline_companies.get(company_id, {})

        # Volume spike
        volume_anomaly = detector.detect_volume_spike(
            subject=company_id,
            subject_type="company",
            current=stats["count"],
            baselines=company_baseline,
        )
        if volume_anomaly:
            anomalies.append(volume_anomaly)

        # Sentiment shift
        if stats["count"] >= 3:  # 至少 3 則才有意義
            sentiment_anomaly = detector.detect_sentiment_shift(
                subject=company_id,
                subject_type="company",
                current=stats["sentiment_avg"],
                baselines={
                    "7d_avg": company_baseline.get("sentiment_7d_avg"),
                    "30d_avg": company_baseline.get("sentiment_30d_avg"),
                },
                event_count=stats["count"],
            )
            if sentiment_anomaly:
                anomalies.append(sentiment_anomaly)

    # 偵測主題異常
    for topic_id, stats in by_topic.items():
        topic_baseline = baseline_topics.get(topic_id, {})

        # Volume spike
        volume_anomaly = detector.detect_volume_spike(
            subject=topic_id,
            subject_type="topic",
            current=stats["count"],
            baselines=topic_baseline,
        )
        if volume_anomaly:
            anomalies.append(volume_anomaly)

        # Sentiment shift
        if stats["count"] >= 3:
            sentiment_anomaly = detector.detect_sentiment_shift(
                subject=topic_id,
                subject_type="topic",
                current=stats["sentiment_avg"],
                baselines={
                    "7d_avg": topic_baseline.get("sentiment_7d_avg"),
                    "30d_avg": topic_baseline.get("sentiment_30d_avg"),
                },
                event_count=stats["count"],
            )
            if sentiment_anomaly:
                anomalies.append(sentiment_anomaly)

        # Topic resurface
        resurface_anomaly = detector.detect_topic_resurface(
            subject=topic_id,
            current=stats["count"],
            last_seen=topic_baseline.get("last_seen"),
            today=date_str,
        )
        if resurface_anomaly:
            anomalies.append(resurface_anomaly)

    # 檢查沒出現在今日但過去出現過的主題
    # （這些可能是「沉寂」的主題，不算 resurface）

    # 排序
    anomalies = detector.sort_anomalies(anomalies)

    return anomalies


def save_metrics(metrics: dict, output_file: Path) -> None:
    """儲存指標"""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="異常偵測腳本")
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
        "--config-dir",
        type=str,
        default="configs",
        help="設定檔目錄",
    )

    args = parser.parse_args()

    metrics_dir = Path(args.metrics_dir)
    baselines_dir = Path(args.baselines_dir)
    config_dir = Path(args.config_dir)

    # 載入今日指標
    metrics_file = metrics_dir / f"{args.date}.json"
    metrics = load_metrics(metrics_file)

    if not metrics:
        print(f"錯誤：找不到 {metrics_file}")
        return

    # 載入歷史基準線
    baselines = load_baselines(baselines_dir)

    # 載入異常偵測器
    detector = load_anomaly_detector(
        config_path=str(config_dir / "anomaly_rules.yml"),
    )

    # 偵測異常
    anomalies = detect_all_anomalies(metrics, baselines, detector, args.date)

    # 更新 metrics
    metrics["anomalies"] = anomalies

    # 儲存
    save_metrics(metrics, metrics_file)

    print(f"異常偵測完成：發現 {len(anomalies)} 個異常")

    # 輸出摘要
    for anomaly in anomalies[:5]:
        print(f"  - [{anomaly['type']}] {anomaly['description']}")


if __name__ == "__main__":
    main()
