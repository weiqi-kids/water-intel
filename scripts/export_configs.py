#!/usr/bin/env python3
"""
將 configs/*.yml 轉換為 site/data/configs/*.json
供前端動態載入使用
"""

import json
import yaml
from pathlib import Path


def main():
    # 路徑設定
    repo_root = Path(__file__).parent.parent
    configs_dir = repo_root / "configs"
    output_dir = repo_root / "site" / "data" / "configs"

    # 確保輸出目錄存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 要轉換的設定檔
    config_files = [
        "companies.yml",
        "topics.yml",
        "sentiment_rules.yml",
        "importance_rules.yml",
        "anomaly_rules.yml",
        "7d_highlights_rules.yml",
    ]

    # 統計資訊（給流程圖用）
    stats = {}

    for config_file in config_files:
        input_path = configs_dir / config_file
        output_path = output_dir / config_file.replace(".yml", ".json")

        if not input_path.exists():
            print(f"跳過 {config_file}（不存在）")
            continue

        with open(input_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"轉換 {config_file} → {output_path.name}")

        # 收集統計資訊
        if config_file == "companies.yml":
            companies = data.get("companies", [])
            stats["company_count"] = len(companies)
            stats["companies"] = [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "short_name": c.get("short_name", c["name"]),
                    "position": c.get("position", "unknown"),
                }
                for c in companies
            ]
            # 計算別名數量
            alias_count = sum(len(c.get("aliases", [])) for c in companies)
            stats["alias_count"] = alias_count

        elif config_file == "topics.yml":
            topics = data.get("topics", {})
            stats["topic_count"] = len(topics)
            stats["topics"] = list(topics.keys())

        elif config_file == "sentiment_rules.yml":
            positive = data.get("positive", {})
            negative = data.get("negative", {})
            negation = data.get("negation", {})
            stats["positive_word_count"] = len(positive.get("strong", [])) + len(
                positive.get("moderate", [])
            )
            stats["negative_word_count"] = len(negative.get("strong", [])) + len(
                negative.get("moderate", [])
            )
            stats["negation_word_count"] = len(negation.get("words", []))

        elif config_file == "importance_rules.yml":
            rules = data.get("rules", [])
            stats["importance_rule_count"] = len(rules)
            stats["base_score"] = data.get("base_score", 0.5)
            stats["max_score"] = data.get("max_score", 1.0)

        elif config_file == "anomaly_rules.yml":
            detection = data.get("anomaly_detection", {})
            thresholds = detection.get("thresholds", {})
            stats["volume_spike_threshold"] = thresholds.get("volume_spike", {}).get(
                "vs_7d_pct", 100
            )
            stats["sentiment_shift_threshold"] = thresholds.get(
                "sentiment_shift", {}
            ).get("delta_7d", 0.5)
            stats["silent_days_threshold"] = thresholds.get("topic_resurface", {}).get(
                "min_silent_days", 14
            )

    # 輸出統計摘要
    stats_path = output_dir / "stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"統計摘要 → {stats_path.name}")

    print(f"\n完成！共轉換 {len(config_files)} 個設定檔")
    print(f"統計：")
    print(f"  - 公司數量: {stats.get('company_count', 0)}")
    print(f"  - 主題數量: {stats.get('topic_count', 0)}")
    print(f"  - 正面詞數: {stats.get('positive_word_count', 0)}")
    print(f"  - 負面詞數: {stats.get('negative_word_count', 0)}")
    print(f"  - 重要性規則數: {stats.get('importance_rule_count', 0)}")


if __name__ == "__main__":
    main()
