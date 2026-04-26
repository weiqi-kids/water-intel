"""
關鍵字匹配引擎

功能：
1. 從文字中匹配主題（topics）
2. 從文字中匹配公司（companies）
3. 根據 companies.yml 的 upstream/downstream 判斷客戶/供應商關係
"""

import re
from typing import Optional
import yaml


class KeywordMatcher:
    """關鍵字匹配引擎"""

    def __init__(
        self,
        topics_config: dict,
        companies_config: dict,
    ):
        """
        Args:
            topics_config: topics.yml 載入的 dict
            companies_config: companies.yml 載入的 dict
        """
        self.topics = topics_config.get("topics", {})
        self.companies = companies_config.get("companies", [])

        # 建立公司 ID -> 公司資料的映射
        self._company_map = {c["id"]: c for c in self.companies}

        # 建立公司名稱/別名 -> 公司 ID 的映射（用於匹配）
        self._company_name_map = self._build_company_name_map()

        # 建立上下游關係映射
        self._upstream_map, self._downstream_map = self._build_relation_maps()

    def _build_company_name_map(self) -> dict[str, str]:
        """建立公司名稱/別名 -> 公司 ID 的映射"""
        name_map = {}
        for company in self.companies:
            company_id = company["id"]

            # 加入主要名稱
            name_map[company["name"].lower()] = company_id
            name_map[company_id.lower()] = company_id

            # 加入別名
            for alias in company.get("aliases", []):
                name_map[alias.lower()] = company_id

        return name_map

    def _build_relation_maps(self) -> tuple[dict, dict]:
        """建立上下游關係映射"""
        upstream_map = {}   # company_id -> [upstream company ids]
        downstream_map = {}  # company_id -> [downstream company ids]

        for company in self.companies:
            company_id = company["id"]
            upstream_map[company_id] = company.get("upstream", [])
            downstream_map[company_id] = company.get("downstream", [])

        return upstream_map, downstream_map

    def match_topics(self, text: str) -> list[str]:
        """
        從文字中匹配主題

        Args:
            text: 要匹配的文字

        Returns:
            匹配到的主題 ID 列表
        """
        matched = []
        text_lower = text.lower()

        for topic_id, config in self.topics.items():
            keywords = config.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    matched.append(topic_id)
                    break  # 一個主題只需匹配一次

        return matched

    def match_companies(self, text: str) -> list[str]:
        """
        從文字中匹配公司

        使用詞邊界匹配，避免 "ase" 配到 "phase" 等誤判。

        Args:
            text: 要匹配的文字

        Returns:
            匹配到的公司 ID 列表
        """
        matched = set()
        text_lower = text.lower()

        for name, company_id in self._company_name_map.items():
            # 判斷是否為純 ASCII（英文/數字）
            is_ascii = all(ord(c) < 128 for c in name)

            if is_ascii and len(name) < 5:
                # 英文短名稱：用 word boundary 避免誤判（如 "ase" 配到 "phase"）
                pattern = r'\b' + re.escape(name) + r'\b'
                if re.search(pattern, text_lower):
                    matched.add(company_id)
            else:
                # 非 ASCII（中文/韓文/日文）或長英文名稱：直接子字串匹配
                if name in text_lower:
                    matched.add(company_id)

        return list(matched)

    def get_customers(self, company_ids: list[str]) -> list[str]:
        """
        根據公司列表，找出可能的客戶（下游）

        Args:
            company_ids: 公司 ID 列表

        Returns:
            客戶公司 ID 列表
        """
        customers = set()

        for company_id in company_ids:
            # 這間公司的下游就是它的客戶
            downstream = self._downstream_map.get(company_id, [])
            for downstream_id in downstream:
                # 如果下游公司也在提及列表中，就是客戶
                if downstream_id in company_ids:
                    customers.add(downstream_id)

        return list(customers)

    def get_suppliers(self, company_ids: list[str]) -> list[str]:
        """
        根據公司列表，找出可能的供應商（上游）

        Args:
            company_ids: 公司 ID 列表

        Returns:
            供應商公司 ID 列表
        """
        suppliers = set()

        for company_id in company_ids:
            # 這間公司的上游就是它的供應商
            upstream = self._upstream_map.get(company_id, [])
            for upstream_id in upstream:
                # 如果上游公司也在提及列表中，就是供應商
                if upstream_id in company_ids:
                    suppliers.add(upstream_id)

        return list(suppliers)

    def build_entities(self, text: str) -> dict:
        """
        從文字中建立完整的 entities 結構

        Args:
            text: 要分析的文字

        Returns:
            entities dict，包含 companies, customers, suppliers
        """
        companies = self.match_companies(text)
        customers = self.get_customers(companies)
        suppliers = self.get_suppliers(companies)

        return {
            "companies": companies,
            "customers": customers,
            "suppliers": suppliers,
        }

    def get_company_position(self, company_id: str) -> Optional[str]:
        """
        取得公司在供應鏈中的位置

        Args:
            company_id: 公司 ID

        Returns:
            位置：upstream, midstream, downstream，或 None
        """
        company = self._company_map.get(company_id)
        if company:
            return company.get("position")
        return None

    def has_upstream_downstream_mention(self, company_ids: list[str]) -> bool:
        """
        檢查是否同時提及上游和下游公司

        Args:
            company_ids: 公司 ID 列表

        Returns:
            是否同時提及上游和下游
        """
        positions = set()
        for company_id in company_ids:
            pos = self.get_company_position(company_id)
            if pos:
                positions.add(pos)

        # 同時有 upstream 和 downstream，或同時有 upstream/midstream 和 downstream
        has_upstream = "upstream" in positions
        has_midstream = "midstream" in positions
        has_downstream = "downstream" in positions

        return (has_upstream or has_midstream) and has_downstream


def load_matcher(
    topics_path: str = "configs/topics.yml",
    companies_path: str = "configs/companies.yml",
) -> KeywordMatcher:
    """
    載入設定檔並建立 KeywordMatcher

    Args:
        topics_path: topics.yml 路徑
        companies_path: companies.yml 路徑

    Returns:
        KeywordMatcher 實例
    """
    with open(topics_path, "r", encoding="utf-8") as f:
        topics_config = yaml.safe_load(f)

    with open(companies_path, "r", encoding="utf-8") as f:
        companies_config = yaml.safe_load(f)

    return KeywordMatcher(topics_config, companies_config)
