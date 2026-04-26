"""
公司官網爬蟲 - 基底類別

使用 Playwright 處理 JavaScript 渲染的頁面。

每間公司的官網結構不同，但要抓的東西類似：
- IR 頁面（法說會、簡報、財報）
- 新聞稿
- 公告

這個 base class 處理共用邏輯：
- Playwright 瀏覽器管理
- 資料格式
- 存檔
- 日誌

子類別只需要定義：
- URL
- 解析邏輯
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import json
import logging

try:
    from bs4 import BeautifulSoup
    from playwright.sync_api import sync_playwright, Page, Browser
except ImportError as e:
    BeautifulSoup = None
    sync_playwright = None
    print(f"Warning: required packages not installed: {e}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CompanyDocument:
    """公司文件標準格式"""
    company_id: str
    doc_type: str  # ir, news, announcement, earnings
    title: str
    url: str
    published_at: Optional[datetime] = None
    content: Optional[str] = None
    attachments: list[str] = field(default_factory=list)  # PDF 連結等
    language: str = "en"
    tags: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        """根據 URL 生成唯一 ID"""
        return hashlib.md5(self.url.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "doc_type": self.doc_type,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "content": self.content,
            "attachments": self.attachments,
            "language": self.language,
            "tags": self.tags,
            "fetched_at": datetime.utcnow().isoformat() + "Z"
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class CompanyFetcher(ABC):
    """公司官網爬蟲基底類別 - 使用 Playwright"""

    company_id: str = "unknown"
    company_name: str = "Unknown"

    # 要抓取的頁面
    ir_url: Optional[str] = None
    news_url: Optional[str] = None

    # Playwright 設定
    headless: bool = True
    timeout: int = 30000  # ms
    wait_for_selector: Optional[str] = None  # 等待特定元素出現

    # Retry 設定
    max_retries: int = 3
    retry_base_delay: float = 2.0  # 秒

    def __init__(self):
        if sync_playwright is None or BeautifulSoup is None:
            raise ImportError("playwright and beautifulsoup4 are required")
        self._browser: Optional[Browser] = None
        self._playwright = None

    def __enter__(self):
        """Context manager 進入"""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 離開"""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def fetch_all(self) -> dict[str, list[CompanyDocument]]:
        """抓取所有資料"""
        result = {}

        with self:
            if self.ir_url:
                result["ir"] = self.fetch_ir()

            if self.news_url:
                result["news"] = self.fetch_news()

        return result

    def fetch_ir(self) -> list[CompanyDocument]:
        """抓取 IR 頁面"""
        if not self.ir_url:
            return []

        html = self._get_page(self.ir_url)
        if not html:
            return []

        return self.parse_ir(html)

    def fetch_news(self) -> list[CompanyDocument]:
        """抓取新聞稿"""
        if not self.news_url:
            return []

        html = self._get_page(self.news_url)
        if not html:
            return []

        docs = self.parse_news(html)

        # 過濾掉沒有 published_at 的事件（通常是抓錯的靜態頁面）
        valid_docs = [d for d in docs if d.published_at is not None]
        skipped = len(docs) - len(valid_docs)
        if skipped > 0:
            logger.warning(f"[{self.company_id}] Skipped {skipped} items without published_at")

        return valid_docs

    @abstractmethod
    def parse_ir(self, html: str) -> list[CompanyDocument]:
        """解析 IR 頁面，子類別必須實作"""
        pass

    @abstractmethod
    def parse_news(self, html: str) -> list[CompanyDocument]:
        """解析新聞稿頁面，子類別必須實作"""
        pass

    def _get_page(self, url: str, wait_selector: Optional[str] = None) -> Optional[str]:
        """使用 Playwright 取得頁面 HTML（含 retry）"""
        import time

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"[{self.company_id}] Fetching {url} (attempt {attempt}/{self.max_retries})")

                if self._browser is None:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=self.headless)
                        page = browser.new_page()
                        html = self._fetch_page_content(page, url, wait_selector)
                        browser.close()
                        return html
                else:
                    page = self._browser.new_page()
                    html = self._fetch_page_content(page, url, wait_selector)
                    page.close()
                    return html

            except Exception as e:
                logger.error(f"[{self.company_id}] Failed to fetch {url} (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    delay = self.retry_base_delay * (2 ** (attempt - 1))
                    logger.info(f"[{self.company_id}] Retrying in {delay:.0f}s...")
                    time.sleep(delay)
                else:
                    logger.error(f"[{self.company_id}] All {self.max_retries} attempts failed for {url}")
                    return None

    def _fetch_page_content(self, page: Page, url: str, wait_selector: Optional[str] = None) -> str:
        """實際抓取頁面內容"""
        page.goto(url, timeout=self.timeout)

        # 等待特定元素或頁面載入完成
        selector = wait_selector or self.wait_for_selector
        if selector:
            try:
                page.wait_for_selector(selector, timeout=self.timeout)
            except Exception:
                logger.warning(f"Selector {selector} not found, continuing anyway")

        # 等待網路請求完成
        page.wait_for_load_state("networkidle", timeout=self.timeout)

        return page.content()

    def _parse_html(self, html: str) -> BeautifulSoup:
        """解析 HTML"""
        return BeautifulSoup(html, 'html.parser')

    def save(self, documents: list[CompanyDocument], output_path: str) -> None:
        """存檔為 JSONL 格式"""
        with open(output_path, 'a', encoding='utf-8') as f:
            for doc in documents:
                f.write(doc.to_json() + '\n')
        logger.info(f"Saved {len(documents)} documents to {output_path}")
