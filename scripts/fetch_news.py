#!/usr/bin/env python3
"""
新聞整合抓取腳本

遵循標準流程：
1. 抓取所有公司新聞 → data/raw/{date}.jsonl
2. 呼叫 enrich_event.py 處理 → data/events/{date}.jsonl
3. 呼叫 generate_metrics.py → data/metrics/{date}.json
4. 呼叫 sync_to_frontend.py → site/data/events.json

用法：
    python scripts/fetch_news.py
    python scripts/fetch_news.py --date 2026-03-14
    python scripts/fetch_news.py --skip-enrich  # 只抓取不處理
"""

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from fetchers import FETCHERS

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 路徑設定
BASE_DIR = Path(__file__).parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"


def fetch_company(company_id: str, fetcher_class) -> list[dict]:
    """抓取單一公司新聞，返回原始格式"""
    docs_list = []

    try:
        logger.info(f"\n[{company_id}] 開始抓取...")
        fetcher = fetcher_class()

        # RSS 類型直接抓取
        rss_fetchers = ['SamsungFetcher', 'NVIDIAFetcher', 'AMDFetcher', 'AppleFetcher']
        if hasattr(fetcher, '_fetch_rss') and fetcher_class.__name__ in rss_fetchers:
            if hasattr(fetcher, 'rss_url') and fetcher.rss_url:
                docs = fetcher._fetch_rss()
            else:
                result = fetcher.fetch_all()
                docs = result.get('news', []) + result.get('ir', [])
        else:
            # Playwright 類型
            result = fetcher.fetch_all()
            docs = result.get('news', []) + result.get('ir', [])

        for doc in docs:
            # 輸出原始格式，讓 enrich_event.py 處理
            raw_doc = {
                "company_id": company_id,
                "title": doc.title,
                "url": doc.url,
                "content": doc.content or "",
                "published_at": doc.published_at.isoformat() if doc.published_at else None,
                "doc_type": doc.doc_type,
                "tags": doc.tags or [],
                "fetched_at": datetime.now().isoformat(),
            }
            docs_list.append(raw_doc)

        logger.info(f"  抓到 {len(docs_list)} 則")

    except Exception as e:
        logger.error(f"  錯誤: {e}")

    return docs_list


def save_raw_docs(docs: list[dict], date_str: str) -> Path:
    """儲存原始文件到 data/raw/{date}.jsonl"""
    output_dir = RAW_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "news.jsonl"

    with open(output_file, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    return output_file


def run_enrich(date_str: str, input_file: Path) -> bool:
    """執行 enrich_event.py"""
    logger.info(f"\n=== 執行 enrich_event.py ===")
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "enrich_event.py"),
        "--date", date_str,
        "--input", str(input_file),
    ]
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def run_metrics(date_str: str) -> bool:
    """執行 generate_metrics.py"""
    logger.info(f"\n=== 執行 generate_metrics.py ===")
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "generate_metrics.py"),
        "--date", date_str,
    ]
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def run_sync_frontend() -> bool:
    """執行 sync_to_frontend.py"""
    logger.info(f"\n=== 執行 sync_to_frontend.py ===")
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "sync_to_frontend.py"),
    ]
    result = subprocess.run(cmd, cwd=str(BASE_DIR))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="新聞整合抓取腳本")
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="處理日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="只抓取不處理",
    )
    args = parser.parse_args()

    date_str = args.date

    logger.info("=== 新聞整合抓取 ===")
    logger.info(f"日期: {date_str}")
    logger.info(f"支援公司: {', '.join(FETCHERS.keys())}")

    all_docs = []

    # 逐一抓取
    for company_id, fetcher_class in FETCHERS.items():
        docs = fetch_company(company_id, fetcher_class)
        all_docs.extend(docs)

    # 去重（依 URL）
    seen_urls = set()
    unique_docs = []
    for doc in all_docs:
        if doc['url'] not in seen_urls:
            seen_urls.add(doc['url'])
            unique_docs.append(doc)

    logger.info(f"\n=== 抓取完成 ===")
    logger.info(f"總共 {len(unique_docs)} 則新聞")

    # 儲存原始文件
    raw_file = save_raw_docs(unique_docs, date_str)
    logger.info(f"儲存至: {raw_file}")

    # 顯示統計
    from collections import Counter
    company_counts = Counter(doc['company_id'] for doc in unique_docs)
    logger.info("\n依公司:")
    for c, count in company_counts.most_common():
        logger.info(f"  {c}: {count} 則")

    if args.skip_enrich:
        logger.info("\n跳過後續處理（--skip-enrich）")
        return

    # 執行後續流程
    if run_enrich(date_str, raw_file):
        run_metrics(date_str)
        run_sync_frontend()

    logger.info("\n=== 全部完成 ===")


if __name__ == "__main__":
    main()
