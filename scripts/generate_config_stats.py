#!/usr/bin/env python3
"""
生成設定檔統計資訊

從各 yml 設定檔讀取並計算統計數據，輸出至 site/data/configs/stats.json
"""

import json
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIGS_DIR = BASE_DIR / "configs"
OUTPUT_FILE = BASE_DIR / "site" / "data" / "configs" / "stats.json"


def load_yaml(filename: str) -> dict:
    """載入 YAML 檔案"""
    filepath = CONFIGS_DIR / filename
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def count_keywords(topics: dict) -> int:
    """計算所有別名/關鍵字數量"""
    count = 0
    for topic_data in topics.values():
        if isinstance(topic_data, dict):
            keywords = topic_data.get("keywords", [])
            count += len(keywords)
    return count


def count_sentiment_words(category: dict) -> int:
    """計算情緒詞數量"""
    count = 0
    if isinstance(category, dict):
        for level in category.values():
            if isinstance(level, list):
                count += len(level)
    return count


def main():
    # 載入設定檔
    companies = load_yaml("companies.yml")
    topics = load_yaml("topics.yml")
    sentiment = load_yaml("sentiment_rules.yml")
    importance = load_yaml("importance_rules.yml")
    anomaly = load_yaml("anomaly_rules.yml")

    # 計算公司統計
    company_list = companies.get("companies", [])
    company_count = len(company_list)

    # 計算主題統計
    topic_dict = topics.get("topics", {})
    topic_count = len(topic_dict)
    alias_count = count_keywords(topic_dict)

    # 計算情緒詞統計
    positive_count = count_sentiment_words(sentiment.get("positive", {}))
    negative_count = count_sentiment_words(sentiment.get("negative", {}))
    negation_words = sentiment.get("negation", {}).get("words", [])
    negation_count = len(negation_words)

    # 計算重要性規則統計
    rules = importance.get("rules", [])
    rule_count = len(rules)

    # 異常偵測閾值
    anomaly_thresholds = anomaly.get("anomaly_detection", {}).get("thresholds", {})
    volume_spike = anomaly_thresholds.get("volume_spike", {}).get("vs_7d_pct", 100)
    sentiment_shift = anomaly_thresholds.get("sentiment_shift", {}).get("delta_7d", 0.5)
    silent_days = anomaly_thresholds.get("topic_resurface", {}).get("min_silent_days", 14)

    # 建立公司列表（供前端使用）
    companies_for_frontend = []
    for c in company_list:
        companies_for_frontend.append({
            "id": c.get("id", ""),
            "short_name": c.get("short_name", c.get("name", "")),
            "tier": c.get("tier", ""),
        })

    # 建立統計結果
    stats = {
        "company_count": company_count,
        "topic_count": topic_count,
        "alias_count": alias_count,
        "positive_word_count": positive_count,
        "negative_word_count": negative_count,
        "negation_word_count": negation_count,
        "importance_rule_count": rule_count,
        "base_score": 0.5,
        "max_score": 1.0,
        "volume_spike_threshold": volume_spike,
        "sentiment_shift_threshold": sentiment_shift,
        "silent_days_threshold": silent_days,
        "companies": companies_for_frontend,
    }

    # 確保輸出目錄存在
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 寫入 JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"統計資料已生成：{OUTPUT_FILE}")
    print(f"  公司數：{company_count}")
    print(f"  主題數：{topic_count}")
    print(f"  別名數：{alias_count}")
    print(f"  正面詞：{positive_count}")
    print(f"  負面詞：{negative_count}")
    print(f"  否定詞：{negation_count}")
    print(f"  規則數：{rule_count}")


if __name__ == "__main__":
    main()
