"""
異常偵測引擎

功能：
1. 新聞量暴增（volume_spike）
2. 情緒急轉（sentiment_shift）
3. 主題重新出現（topic_resurface）

需要歷史基準線（baselines）資料。
資料不足時不觸發異常。
"""

from datetime import datetime, timedelta
from typing import Optional
import yaml


class AnomalyDetector:
    """異常偵測引擎"""

    def __init__(self, config: dict):
        """
        Args:
            config: anomaly_rules.yml 載入的 dict
        """
        detection = config.get("anomaly_detection", {})

        # 最小資料量要求
        self.min_requirements = detection.get("minimum_data_requirements", {})
        self.min_7d = self.min_requirements.get("7d_avg", 5)
        self.min_30d = self.min_requirements.get("30d_avg", 20)
        self.min_yoy = self.min_requirements.get("yoy", 300)

        # 閾值設定
        thresholds = detection.get("thresholds", {})
        self.volume_thresholds = thresholds.get("volume_spike", {})
        self.sentiment_thresholds = thresholds.get("sentiment_shift", {})
        self.resurface_thresholds = thresholds.get("topic_resurface", {})

        # 優先級
        self.priority = detection.get("priority", {})

    def detect_volume_spike(
        self,
        subject: str,
        subject_type: str,  # "company" or "topic"
        current: int,
        baselines: dict,
    ) -> Optional[dict]:
        """
        偵測新聞量暴增

        Args:
            subject: 主體 ID（公司或主題）
            subject_type: "company" 或 "topic"
            current: 今日數量
            baselines: {
                "7d_avg": float,
                "30d_avg": float,
                "yoy_same_week": int,
                "data_days": int,  # 有幾天的資料
            }

        Returns:
            異常 dict，或 None
        """
        # 最小絕對數量
        min_absolute = self.volume_thresholds.get("min_absolute", 3)
        if current < min_absolute:
            return None

        deviations = {}
        triggered = False

        # 檢查 7 日均值
        avg_7d = baselines.get("7d_avg")
        data_days = baselines.get("data_days", 0)

        if avg_7d and data_days >= self.min_7d and avg_7d > 0:
            pct_7d = ((current - avg_7d) / avg_7d) * 100
            deviations["vs_7d"] = f"+{pct_7d:.0f}%" if pct_7d > 0 else f"{pct_7d:.0f}%"

            threshold_7d = self.volume_thresholds.get("vs_7d_pct", 100)
            if pct_7d >= threshold_7d:
                triggered = True

        # 檢查 30 日均值
        avg_30d = baselines.get("30d_avg")
        if avg_30d and data_days >= self.min_30d and avg_30d > 0:
            pct_30d = ((current - avg_30d) / avg_30d) * 100
            deviations["vs_30d"] = f"+{pct_30d:.0f}%" if pct_30d > 0 else f"{pct_30d:.0f}%"

            threshold_30d = self.volume_thresholds.get("vs_30d_pct", 80)
            if pct_30d >= threshold_30d:
                triggered = True

        # 檢查去年同期
        yoy = baselines.get("yoy_same_week")
        if yoy is not None and data_days >= self.min_yoy and yoy > 0:
            pct_yoy = ((current - yoy) / yoy) * 100
            deviations["vs_yoy"] = f"+{pct_yoy:.0f}%" if pct_yoy > 0 else f"{pct_yoy:.0f}%"

            threshold_yoy = self.volume_thresholds.get("vs_yoy_pct", 150)
            if pct_yoy >= threshold_yoy:
                triggered = True

        if not triggered:
            return None

        return {
            "type": "volume_spike",
            "subject": subject,
            "subject_type": subject_type,
            "metric": "event_count",
            "current": current,
            "baselines": {
                "7d_avg": baselines.get("7d_avg"),
                "30d_avg": baselines.get("30d_avg"),
                "yoy_same_week": baselines.get("yoy_same_week"),
            },
            "deviations": deviations,
            "description": f"{subject} 新聞量異常增加",
            "priority": self.priority.get("volume_spike", 1),
        }

    def detect_sentiment_shift(
        self,
        subject: str,
        subject_type: str,
        current: float,
        baselines: dict,
        event_count: int,
    ) -> Optional[dict]:
        """
        偵測情緒急轉

        Args:
            subject: 主體 ID
            subject_type: "company" 或 "topic"
            current: 今日情緒分數
            baselines: {
                "7d_avg": float,
                "30d_avg": float,
            }
            event_count: 今日事件數（太少不偵測）

        Returns:
            異常 dict，或 None
        """
        min_events = self.sentiment_thresholds.get("min_events", 3)
        if event_count < min_events:
            return None

        deviations = {}
        triggered = False

        # 檢查與 7 日均值的差距
        avg_7d = baselines.get("7d_avg")
        if avg_7d is not None:
            delta_7d = current - avg_7d
            deviations["vs_7d"] = round(delta_7d, 2)

            threshold_7d = self.sentiment_thresholds.get("delta_7d", 0.5)
            if abs(delta_7d) >= threshold_7d:
                triggered = True

        # 檢查與 30 日均值的差距
        avg_30d = baselines.get("30d_avg")
        if avg_30d is not None:
            delta_30d = current - avg_30d
            deviations["vs_30d"] = round(delta_30d, 2)

            threshold_30d = self.sentiment_thresholds.get("delta_30d", 0.4)
            if abs(delta_30d) >= threshold_30d:
                triggered = True

        if not triggered:
            return None

        # 決定描述
        if current > 0 and (avg_7d or 0) < 0:
            shift_desc = "從負面轉為正面"
        elif current < 0 and (avg_7d or 0) > 0:
            shift_desc = "從正面轉為負面"
        elif current > (avg_7d or 0):
            shift_desc = "情緒明顯轉好"
        else:
            shift_desc = "情緒明顯轉差"

        return {
            "type": "sentiment_shift",
            "subject": subject,
            "subject_type": subject_type,
            "metric": "sentiment_avg",
            "current": round(current, 2),
            "baselines": {
                "7d_avg": baselines.get("7d_avg"),
                "30d_avg": baselines.get("30d_avg"),
            },
            "deviations": deviations,
            "description": f"{subject} {shift_desc}",
            "priority": self.priority.get("sentiment_shift", 2),
        }

    def detect_topic_resurface(
        self,
        subject: str,
        current: int,
        last_seen: Optional[str],  # ISO date string
        today: str,  # ISO date string
    ) -> Optional[dict]:
        """
        偵測主題重新出現

        Args:
            subject: 主題 ID
            current: 今日數量
            last_seen: 上次出現的日期（ISO 格式）
            today: 今天日期（ISO 格式）

        Returns:
            異常 dict，或 None
        """
        min_events = self.resurface_thresholds.get("min_events", 2)
        if current < min_events:
            return None

        if not last_seen:
            # 從來沒出現過，這是首次，算新出現
            return {
                "type": "topic_resurface",
                "subject": subject,
                "subject_type": "topic",
                "current": current,
                "baselines": {
                    "last_seen": None,
                    "days_since": None,
                },
                "description": f"「{subject}」主題首次出現",
                "priority": self.priority.get("topic_resurface", 3),
            }

        # 計算沉寂天數
        try:
            last_date = datetime.fromisoformat(last_seen)
            today_date = datetime.fromisoformat(today)
            days_since = (today_date - last_date).days
        except ValueError:
            return None

        min_silent_days = self.resurface_thresholds.get("min_silent_days", 14)
        if days_since < min_silent_days:
            return None

        return {
            "type": "topic_resurface",
            "subject": subject,
            "subject_type": "topic",
            "current": current,
            "baselines": {
                "last_seen": last_seen,
                "days_since": days_since,
            },
            "description": f"「{subject}」主題沉寂 {days_since} 天後重新出現",
            "priority": self.priority.get("topic_resurface", 3),
        }

    def sort_anomalies(self, anomalies: list[dict]) -> list[dict]:
        """
        按優先級排序異常

        Args:
            anomalies: 異常列表

        Returns:
            排序後的異常列表
        """
        return sorted(anomalies, key=lambda x: x.get("priority", 99))


def load_anomaly_detector(
    config_path: str = "configs/anomaly_rules.yml",
) -> AnomalyDetector:
    """
    載入設定檔並建立 AnomalyDetector

    Args:
        config_path: anomaly_rules.yml 路徑

    Returns:
        AnomalyDetector 實例
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return AnomalyDetector(config)
