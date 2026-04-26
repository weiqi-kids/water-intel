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
import requests
import xml.etree.ElementTree as ET

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

    # Fetch mode: "rss" | "http" | "playwright"
    fetch_mode: str = "http"
    ir_rss_url: Optional[str] = None

    # HTTP settings
    http_headers: dict = None
    http_timeout: int = 30

    # Retry 設定
    max_retries: int = 1
    retry_base_delay: float = 2.0  # 秒

    def __init__(self):
        self._browser: Optional[object] = None
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
        """Dispatch to the appropriate fetch method based on fetch_mode."""
        if self.fetch_mode == "rss" and self.ir_rss_url:
            return self._fetch_via_rss()
        elif self.fetch_mode == "http" and self.news_url:
            return self._fetch_via_http()
        else:
            return self._fetch_via_playwright()

    def _fetch_via_playwright(self) -> dict[str, list[CompanyDocument]]:
        """Original Playwright-based fetch (fallback)."""
        if sync_playwright is None or BeautifulSoup is None:
            logger.error(f"[{self.company_id}] Playwright/BS4 not installed, skipping")
            return {}
        result = {}
        with self:
            if self.ir_url:
                result["ir"] = self.fetch_ir()
            if self.news_url:
                result["news"] = self.fetch_news()
        return result

    def _fetch_via_http(self) -> dict[str, list[CompanyDocument]]:
        """Fetch news page via plain HTTP + BeautifulSoup (no JS rendering)."""
        headers = self.http_headers or {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        result = {}
        if self.news_url:
            try:
                logger.info(f"[{self.company_id}] HTTP fetch: {self.news_url}")
                resp = requests.get(self.news_url, timeout=self.http_timeout,
                                    headers=headers)
                resp.raise_for_status()
                docs = self.parse_news(resp.text)
                valid_docs = [d for d in docs if d.published_at is not None]
                skipped = len(docs) - len(valid_docs)
                if skipped > 0:
                    logger.warning(f"[{self.company_id}] Skipped {skipped} items without published_at")
                result["news"] = valid_docs
            except Exception as e:
                logger.error(f"[{self.company_id}] HTTP fetch failed: {e}")
                result["news"] = []
        return result

    def _fetch_via_rss(self) -> dict[str, list[CompanyDocument]]:
        """Fetch company news from IR RSS feed directly."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; IntelBot/1.0)"}
        docs = []
        try:
            logger.info(f"[{self.company_id}] RSS fetch: {self.ir_rss_url}")
            resp = requests.get(self.ir_rss_url, timeout=self.http_timeout,
                                headers=headers)
            resp.raise_for_status()
            docs = self._parse_rss_xml(resp.text)
        except Exception as e:
            logger.error(f"[{self.company_id}] RSS fetch failed: {e}")
        return {"ir": docs}

    def _parse_rss_xml(self, xml_text: str) -> list[CompanyDocument]:
        """Parse RSS 2.0 or Atom feed XML into CompanyDocument list."""
        from email.utils import parsedate_to_datetime

        docs = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"[{self.company_id}] RSS XML parse error: {e}")
            return []

        # Try RSS 2.0 first
        items = root.findall(".//item")
        if not items:
            # Try Atom
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            items = root.findall(".//atom:entry", ns)

        for item in items[:20]:
            title = self._rss_text(item, "title") or self._rss_text(
                item, "{http://www.w3.org/2005/Atom}title"
            )
            link = self._rss_text(item, "link") or ""
            if not link:
                link_el = item.find("{http://www.w3.org/2005/Atom}link")
                if link_el is not None:
                    link = link_el.get("href", "")

            pub_str = (
                self._rss_text(item, "pubDate")
                or self._rss_text(item, "{http://www.w3.org/2005/Atom}updated")
                or ""
            )
            published_at = None
            if pub_str:
                try:
                    published_at = parsedate_to_datetime(pub_str)
                except Exception:
                    try:
                        published_at = datetime.fromisoformat(
                            pub_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

            desc = (
                self._rss_text(item, "description")
                or self._rss_text(item, "{http://www.w3.org/2005/Atom}summary")
                or ""
            )

            if title and link:
                docs.append(CompanyDocument(
                    company_id=self.company_id,
                    doc_type="ir",
                    title=title.strip(),
                    url=link.strip(),
                    published_at=published_at,
                    content=desc[:500] if desc else None,
                    language="en",
                ))

        return docs

    @staticmethod
    def _rss_text(element, tag: str) -> Optional[str]:
        """Extract text from an XML element's child tag."""
        child = element.find(tag)
        return child.text if child is not None and child.text else None

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
        """Fetch page content via Playwright."""
        page.goto(url, timeout=self.timeout)

        selector = wait_selector or self.wait_for_selector
        if selector:
            try:
                page.wait_for_selector(selector, timeout=self.timeout)
            except Exception:
                logger.warning(f"Selector {selector} not found, continuing anyway")

        # Use domcontentloaded instead of networkidle for stability
        page.wait_for_load_state("domcontentloaded", timeout=self.timeout)

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
