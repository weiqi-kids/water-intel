#!/usr/bin/env python3
"""
股價增量抓取

邏輯：
1. 讀取 metadata，知道每檔股票已有資料範圍 [earliest, latest]
2. 每次運行：
   - 補最新：latest+1 → today
   - 補歷史：earliest-3個月 → earliest
3. 合併存檔，更新範圍
4. 重複直到歷史資料抓完
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

try:
    import yfinance as yf
    import yaml
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install yfinance pyyaml")
    exit(1)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# 路徑設定
BASE_DIR = Path(__file__).parent.parent
CONFIG_FILE = BASE_DIR / "configs" / "companies.yml"
DATA_DIR = BASE_DIR / "data"
STOCKS_FILE = DATA_DIR / "normalized" / "stocks.json"
METADATA_FILE = DATA_DIR / "normalized" / "stocks_metadata.json"

# 設定
HISTORY_CHUNK_MONTHS = 3  # 每次往前抓幾個月


def load_companies() -> dict[str, str]:
    """載入公司與 ETF 設定，返回 {ticker: id}

    ETF id 會加上 etf_ 前綴避免碰撞，例如 etf_smh
    """
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tickers = {}
    for c in config.get("companies", []):
        if c.get("ticker"):
            tickers[c["ticker"]] = c["id"]
    for etf in config.get("etfs", []):
        if etf.get("ticker"):
            tickers[etf["ticker"]] = f"etf_{etf['id']}"
    return tickers


def load_metadata() -> dict:
    """載入股票資料範圍 metadata"""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_metadata(metadata: dict):
    """存檔 metadata"""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)


def load_stocks_data() -> dict:
    """載入現有股價資料"""
    if STOCKS_FILE.exists():
        with open(STOCKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_stocks_data(data: dict):
    """存檔股價資料"""
    STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


FRONTEND_STOCKS_FILE = BASE_DIR / "site" / "data" / "stocks.json"
FRONTEND_MAX_DAYS = 730  # 前端只載入最近 2 年


def save_frontend_stocks(data: dict):
    """產生前端用的裁切版 stocks.json（最近 2 年）"""
    cutoff = (date.today() - timedelta(days=FRONTEND_MAX_DAYS)).isoformat()
    trimmed = {}
    for company_id, prices in data.items():
        trimmed[company_id] = [p for p in prices if p["date"] >= cutoff]
    FRONTEND_STOCKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FRONTEND_STOCKS_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)
    total = sum(len(v) for v in trimmed.values())
    logger.info(f"前端版: {FRONTEND_STOCKS_FILE} ({total} 筆, cutoff={cutoff})")



def fetch_stock_range(ticker: str, start: date, end: date) -> list[dict]:
    """抓取指定日期範圍的股價"""
    try:
        stock = yf.Ticker(ticker)
        # yfinance end 是 exclusive，所以 +1 天
        hist = stock.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat()
        )

        if hist.empty:
            return []

        prices = []
        for idx, row in hist.iterrows():
            prices.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"])
            })
        return prices

    except Exception as e:
        logger.warning(f"  Error fetching {ticker}: {e}")
        return []


def merge_prices(existing: list[dict], new_prices: list[dict]) -> list[dict]:
    """合併股價資料，按日期排序去重"""
    # 用 date 作為 key 去重
    by_date = {}
    for p in existing:
        by_date[p["date"]] = p
    for p in new_prices:
        by_date[p["date"]] = p

    # 按日期排序
    return sorted(by_date.values(), key=lambda x: x["date"])


def fetch_incremental(ticker: str, company_id: str, metadata: dict, stocks_data: dict) -> bool:
    """
    增量抓取單檔股票

    Returns:
        bool: True 如果有抓到新資料
    """
    today = date.today()

    # 取得該股票的 metadata
    stock_meta = metadata.get(company_id, {})
    earliest_str = stock_meta.get("earliest")
    latest_str = stock_meta.get("latest")
    history_complete = stock_meta.get("history_complete", False)

    # 現有資料
    existing_prices = stocks_data.get(company_id, [])
    new_prices = []

    # === 1. 補最新資料 ===
    if latest_str:
        latest = date.fromisoformat(latest_str)
        if latest < today:
            # 抓 latest+1 到 today
            fetch_start = latest + timedelta(days=1)
            logger.info(f"  補最新: {fetch_start} → {today}")
            prices = fetch_stock_range(ticker, fetch_start, today)
            if prices:
                new_prices.extend(prices)
                logger.info(f"    抓到 {len(prices)} 天")
    else:
        # 第一次抓，抓今天
        logger.info(f"  首次抓取: {today}")
        prices = fetch_stock_range(ticker, today, today)
        if prices:
            new_prices.extend(prices)
            logger.info(f"    抓到 {len(prices)} 天")

    # === 2. 補歷史資料（如果還沒抓完）===
    if not history_complete:
        if earliest_str:
            earliest = date.fromisoformat(earliest_str)
        else:
            earliest = today

        # 往前 3 個月
        history_end = earliest - timedelta(days=1)
        history_start = earliest - timedelta(days=HISTORY_CHUNK_MONTHS * 30)

        if history_start < date(2000, 1, 1):
            history_start = date(2000, 1, 1)

        if history_end >= history_start:
            logger.info(f"  補歷史: {history_start} → {history_end}")
            prices = fetch_stock_range(ticker, history_start, history_end)
            if prices:
                new_prices.extend(prices)
                logger.info(f"    抓到 {len(prices)} 天")
            else:
                # 沒抓到資料，可能已經到最早了
                logger.info(f"    無更早資料，歷史完成")
                stock_meta["history_complete"] = True

    # === 3. 合併並更新 ===
    if new_prices:
        merged = merge_prices(existing_prices, new_prices)
        stocks_data[company_id] = merged

        # 更新 metadata
        all_dates = [p["date"] for p in merged]
        stock_meta["earliest"] = min(all_dates)
        stock_meta["latest"] = max(all_dates)
        stock_meta["count"] = len(merged)
        metadata[company_id] = stock_meta

        return True

    return False


def main():
    logger.info("=== 股價增量抓取 ===\n")

    # 載入設定
    tickers = load_companies()
    logger.info(f"共 {len(tickers)} 檔股票\n")

    # 載入現有資料
    metadata = load_metadata()
    stocks_data = load_stocks_data()

    # 逐一抓取
    updated = 0
    for ticker, company_id in tickers.items():
        logger.info(f"[{company_id}] {ticker}")

        if fetch_incremental(ticker, company_id, metadata, stocks_data):
            updated += 1
            meta = metadata.get(company_id, {})
            logger.info(f"    範圍: {meta.get('earliest')} ~ {meta.get('latest')} ({meta.get('count')} 天)")
        else:
            logger.info(f"    無新資料")
        print()

    # 存檔
    save_stocks_data(stocks_data)
    save_frontend_stocks(stocks_data)
    save_metadata(metadata)

    logger.info(f"=== 完成 ===")
    logger.info(f"更新 {updated} 檔股票")
    logger.info(f"存檔: {STOCKS_FILE}")
    logger.info(f"Metadata: {METADATA_FILE}")


if __name__ == "__main__":
    main()
