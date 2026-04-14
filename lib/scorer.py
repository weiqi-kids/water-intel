"""
重要性評分引擎

功能：
1. 根據規則計算事件重要性分數
2. 基礎分數 0.5，加上各規則分數，上限 1.0
3. 記錄觸發的規則作為理由

不需要 LLM，純規則引擎。
"""

from typing import Callable
import yaml


class ImportanceScorer:
    """重要性評分引擎"""

    def __init__(
        self,
        rules_config: dict,
        matcher=None,
    ):
        """
        Args:
            rules_config: importance_rules.yml 載入的 dict
            matcher: KeywordMatcher 實例（用於判斷供應鏈關係）
        """
        self.rules = rules_config.get("rules", [])
        self.matcher = matcher
        self.base_score = 0.5

        # 建立條件評估器
        self._evaluators = self._build_evaluators()

    def _build_evaluators(self) -> dict[str, Callable]:
        """
        建立條件字串 -> 評估函數的映射

        支援的條件格式：
        - "entities.companies.length > 1"
        - "'hbm' in topics"
        - "'dram_price' in topics or 'nand_price' in topics"
        - "abs(sentiment.score) > 0.7"
        - "has_upstream_downstream_mention"
        """
        return {
            "entities.companies.length > 1": self._eval_multi_company,
            "'hbm' in topics": self._eval_topic_hbm,
            "'dram_price' in topics or 'nand_price' in topics": self._eval_topic_price,
            "'earnings' in topics": self._eval_topic_earnings,
            "abs(sentiment.score) > 0.7": self._eval_extreme_sentiment,
            "has_upstream_downstream_mention": self._eval_upstream_downstream,
            # 記憶體產業特有
            "'capacity' in topics or 'capex' in topics": self._eval_topic_capacity,
            "'ai_server' in topics": self._eval_topic_ai_server,
            "'advanced_packaging' in topics": self._eval_topic_advanced_packaging,
            "'ai_memory' in topics": self._eval_topic_ai_memory,
        }

    def _eval_multi_company(self, event: dict) -> bool:
        """多公司提及"""
        companies = event.get("entities", {}).get("companies", [])
        return len(companies) > 1

    def _eval_topic_hbm(self, event: dict) -> bool:
        """涉及 HBM"""
        topics = event.get("topics", [])
        return "hbm" in topics

    def _eval_topic_price(self, event: dict) -> bool:
        """涉及價格"""
        topics = event.get("topics", [])
        return "dram_price" in topics or "nand_price" in topics

    def _eval_topic_earnings(self, event: dict) -> bool:
        """涉及財報"""
        topics = event.get("topics", [])
        return "earnings" in topics

    def _eval_extreme_sentiment(self, event: dict) -> bool:
        """情緒極端"""
        sentiment = event.get("sentiment", {})
        score = sentiment.get("score", 0)
        return abs(score) > 0.7

    def _eval_upstream_downstream(self, event: dict) -> bool:
        """供應鏈上下游同時提及"""
        if not self.matcher:
            return False

        companies = event.get("entities", {}).get("companies", [])
        return self.matcher.has_upstream_downstream_mention(companies)

    def _eval_topic_capacity(self, event: dict) -> bool:
        """涉及產能或資本支出"""
        topics = event.get("topics", [])
        return "capacity" in topics or "capex" in topics

    def _eval_topic_ai_server(self, event: dict) -> bool:
        """涉及 AI 伺服器"""
        topics = event.get("topics", [])
        return "ai_server" in topics

    def _eval_topic_advanced_packaging(self, event: dict) -> bool:
        """涉及先進封裝"""
        topics = event.get("topics", [])
        return "advanced_packaging" in topics

    def _eval_topic_ai_memory(self, event: dict) -> bool:
        """涉及 AI 記憶體"""
        topics = event.get("topics", [])
        return "ai_memory" in topics

    def score(self, event: dict) -> dict:
        """
        計算事件的重要性分數

        Args:
            event: 事件 dict，需包含 entities, topics, sentiment

        Returns:
            {
                "score": float (0 to 1),
                "reasons": ["觸發的規則名稱", ...]
            }
        """
        total_score = self.base_score
        reasons = []

        for rule in self.rules:
            condition = rule.get("condition", "")
            rule_score = rule.get("score", 0)
            rule_name = rule.get("name", condition)

            # 找對應的評估器
            evaluator = self._evaluators.get(condition)

            if evaluator:
                try:
                    if evaluator(event):
                        total_score += rule_score
                        reasons.append(rule_name)
                except Exception:
                    # 評估失敗時跳過這條規則
                    pass

        # 限制在 [0, 1]
        final_score = max(0.0, min(1.0, total_score))

        return {
            "score": round(final_score, 2),
            "reasons": reasons,
        }

    def add_custom_evaluator(
        self,
        condition: str,
        evaluator: Callable[[dict], bool],
    ) -> None:
        """
        新增自訂的條件評估器

        Args:
            condition: 條件字串（要與 rules 中的 condition 對應）
            evaluator: 評估函數，接受 event dict，回傳 bool
        """
        self._evaluators[condition] = evaluator


def load_importance_scorer(
    rules_path: str = "configs/importance_rules.yml",
    matcher=None,
) -> ImportanceScorer:
    """
    載入設定檔並建立 ImportanceScorer

    Args:
        rules_path: importance_rules.yml 路徑
        matcher: KeywordMatcher 實例

    Returns:
        ImportanceScorer 實例
    """
    with open(rules_path, "r", encoding="utf-8") as f:
        rules_config = yaml.safe_load(f)

    return ImportanceScorer(rules_config, matcher)
