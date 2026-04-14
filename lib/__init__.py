"""
Templates lib - 通用分析工具庫

這是骨架版本，各 repo 複製後可客製化。
"""

from .matcher import KeywordMatcher
from .sentiment import SentimentAnalyzer
from .scorer import ImportanceScorer
from .anomaly import AnomalyDetector

__all__ = [
    "KeywordMatcher",
    "SentimentAnalyzer",
    "ImportanceScorer",
    "AnomalyDetector",
]
