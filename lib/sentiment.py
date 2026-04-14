"""
情緒分析引擎

功能：
1. 關鍵字匹配計算情緒分數
2. 否定詞處理（反轉情緒）
3. 正規化到 [-1, 1]

不需要 LLM，純規則引擎。
"""

import re
from typing import Optional
import yaml


class SentimentAnalyzer:
    """情緒分析引擎"""

    def __init__(self, rules: dict):
        """
        Args:
            rules: sentiment_rules.yml 載入的 dict
        """
        # 正面詞
        self.positive_strong = rules.get("positive", {}).get("strong", [])
        self.positive_moderate = rules.get("positive", {}).get("moderate", [])

        # 負面詞
        self.negative_strong = rules.get("negative", {}).get("strong", [])
        self.negative_moderate = rules.get("negative", {}).get("moderate", [])

        # 否定詞
        negation = rules.get("negation", {})
        self.negation_words = negation.get("words", [])
        self.negation_window = negation.get("window", 5)

        # 建立詞 -> 分數映射
        self._word_scores = self._build_word_scores()

    def _build_word_scores(self) -> dict[str, float]:
        """建立詞 -> 分數的映射"""
        scores = {}

        for word in self.positive_strong:
            scores[word.lower()] = 1.0
        for word in self.positive_moderate:
            scores[word.lower()] = 0.5
        for word in self.negative_strong:
            scores[word.lower()] = -1.0
        for word in self.negative_moderate:
            scores[word.lower()] = -0.5

        return scores

    def _tokenize(self, text: str) -> list[str]:
        """
        簡易斷詞

        中文：逐字切割後嘗試匹配關鍵字
        英文：空格切割

        實際上我們用子字串匹配，這裡主要是為了否定詞偵測
        """
        # 用空格和標點切割
        tokens = re.split(r'[\s,，。！？!?;；:：、]+', text)
        return [t.strip() for t in tokens if t.strip()]

    def _find_keyword_positions(self, text: str) -> list[tuple[str, int, float]]:
        """
        找出文字中所有情緒詞的位置

        Returns:
            [(keyword, position_index, score), ...]
        """
        text_lower = text.lower()
        tokens = self._tokenize(text)

        results = []

        # 對每個情緒詞檢查是否出現在文字中
        for word, score in self._word_scores.items():
            if word in text_lower:
                # 找出大概在哪個 token 位置
                # 這是近似值，用於否定詞偵測
                pos = self._estimate_position(tokens, word)
                results.append((word, pos, score))

        return results

    def _estimate_position(self, tokens: list[str], keyword: str) -> int:
        """估計關鍵字在 token 序列中的位置"""
        keyword_lower = keyword.lower()

        for i, token in enumerate(tokens):
            if keyword_lower in token.lower():
                return i

        # 找不到的話，檢查是否跨 token
        combined = ""
        for i, token in enumerate(tokens):
            combined += token.lower()
            if keyword_lower in combined:
                return i

        return len(tokens) // 2  # fallback

    def _has_negation_nearby(
        self,
        tokens: list[str],
        pos: int,
    ) -> bool:
        """
        檢查 pos 位置前後 window 範圍內是否有否定詞

        Args:
            tokens: token 序列
            pos: 要檢查的位置

        Returns:
            是否有否定詞
        """
        start = max(0, pos - self.negation_window)
        end = min(len(tokens), pos + self.negation_window + 1)

        for i in range(start, end):
            if i != pos:
                token_lower = tokens[i].lower()
                for neg_word in self.negation_words:
                    if neg_word.lower() in token_lower:
                        return True

        return False

    def analyze(self, text: str) -> dict:
        """
        分析文字的情緒

        Args:
            text: 要分析的文字

        Returns:
            {
                "label": "positive" | "neutral" | "negative",
                "score": float (-1 to 1),
                "keywords": ["匹配到的詞", "[否定]被反轉的詞", ...]
            }
        """
        if not text:
            return {
                "label": "neutral",
                "score": 0.0,
                "keywords": [],
            }

        tokens = self._tokenize(text)
        keyword_positions = self._find_keyword_positions(text)

        total_score = 0.0
        keywords = []

        for keyword, pos, base_score in keyword_positions:
            # 檢查是否被否定詞反轉
            if self._has_negation_nearby(tokens, pos):
                final_score = -base_score
                keywords.append(f"[否定]{keyword}")
            else:
                final_score = base_score
                keywords.append(keyword)

            total_score += final_score

        # 正規化到 [-1, 1]
        # 用 tanh-like 曲線，避免極端值
        if len(keyword_positions) > 0:
            avg_score = total_score / len(keyword_positions)
            # 限制在 [-1, 1]
            normalized = max(-1.0, min(1.0, avg_score))
        else:
            normalized = 0.0

        # 決定標籤
        if normalized > 0.2:
            label = "positive"
        elif normalized < -0.2:
            label = "negative"
        else:
            label = "neutral"

        return {
            "label": label,
            "score": round(normalized, 2),
            "keywords": keywords,
        }

    def get_topic_sentiment_keywords(
        self,
        text: str,
        topic_config: dict,
    ) -> Optional[str]:
        """
        根據主題特定的情緒詞判斷情緒

        有些主題有特定的正負面詞，例如價格：
        - positive: ["上漲", "漲價"]
        - negative: ["下跌", "跌價"]

        Args:
            text: 要分析的文字
            topic_config: 主題設定（包含 sentiment_keywords）

        Returns:
            "positive", "negative", 或 None
        """
        sentiment_keywords = topic_config.get("sentiment_keywords", {})
        if not sentiment_keywords:
            return None

        text_lower = text.lower()

        positive_words = sentiment_keywords.get("positive", [])
        negative_words = sentiment_keywords.get("negative", [])

        has_positive = any(w.lower() in text_lower for w in positive_words)
        has_negative = any(w.lower() in text_lower for w in negative_words)

        if has_positive and not has_negative:
            return "positive"
        elif has_negative and not has_positive:
            return "negative"
        else:
            return None


def load_sentiment_analyzer(
    rules_path: str = "configs/sentiment_rules.yml",
) -> SentimentAnalyzer:
    """
    載入設定檔並建立 SentimentAnalyzer

    Args:
        rules_path: sentiment_rules.yml 路徑

    Returns:
        SentimentAnalyzer 實例
    """
    with open(rules_path, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f)

    return SentimentAnalyzer(rules)
