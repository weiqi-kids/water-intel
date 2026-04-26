"""
Energy Recovery 官網爬蟲
"""

from datetime import datetime
from typing import Optional
import logging

from .base import CompanyFetcher, CompanyDocument

logger = logging.getLogger(__name__)


class EnergyRecoveryFetcher(CompanyFetcher):
    """Energy Recovery 爬蟲"""

    company_id = "energy_recovery"
    company_name = "Energy Recovery"
    news_url = "https://www.energyrecovery.com/news"

    def parse_news(self, html: str) -> list[CompanyDocument]:
        soup = self._parse_html(html)
        documents = []
        selectors = [
            "article", "[class*='press']", "[class*='news-item']",
            "[class*='release']", ".media-item", ".post-item", "li.item",
        ]
        articles = []
        for sel in selectors:
            articles = soup.select(sel)
            if articles:
                break
        for article in articles[:30]:
            title_elem = article.select_one("h2 a, h3 a, h4 a, a.title, .title a")
            if not title_elem:
                heading = article.select_one("h2, h3, h4")
                link = article.select_one("a[href]")
                if heading and link:
                    title = heading.get_text(strip=True)
                    url = link.get("href", "")
                elif link:
                    title = link.get_text(strip=True)
                    url = link.get("href", "")
                else:
                    continue
            else:
                title = title_elem.get_text(strip=True)
                url = title_elem.get("href", "")
            if not title or len(title) < 5:
                continue
            if url and not url.startswith("http"):
                url = "https://www.energyrecovery.com" + url
            date_elem = article.select_one("time, .date, [class*='date']")
            published_at = None
            if date_elem:
                dt_str = date_elem.get("datetime") or date_elem.get_text(strip=True)
                if dt_str:
                    try:
                        published_at = datetime.fromisoformat(dt_str[:10])
                    except (ValueError, TypeError):
                        pass
            doc = CompanyDocument(
                company_id=self.company_id,
                doc_type="news",
                title=title,
                url=url,
                published_at=published_at,
                language="en",
                tags=["news"],
            )
            documents.append(doc)
        logger.info(f"Parsed {len(documents)} news from Energy Recovery")
        return documents

    def parse_ir(self, html: str) -> list[CompanyDocument]:
        return []


if __name__ == "__main__":
    fetcher = EnergyRecoveryFetcher()
    result = fetcher.fetch_all()
    for doc_type, docs in result.items():
        print(f"{doc_type}: {len(docs)} documents")
        for doc in docs[:5]:
            print(f"  [{doc.published_at}] {doc.title[:80]}")
