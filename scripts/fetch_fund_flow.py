#!/usr/bin/env python3
"""
ETF 資金流向指標

計算半導體 ETF 的資金流向：
  Fund Flow = Price Change * Volume（資金流量代理指標）

正向流 = 價格上漲 + 高成交量（資金流入）
負向流 = 價格下跌 + 高成交量（資金流出）

輸出：
  - data/fund_flow/latest.json
  - site/data/fund_flow.json
"""

import json
import logging
from datetime import datetime
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("Missing dependency: yfinance")
    print("Run: pip install yfinance")
    exit(1)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
STOCKS_FILE = BASE_DIR / "data" / "normalized" / "stocks.json"
OUTPUT_FILE = BASE_DIR / "data" / "fund_flow" / "latest.json"
FRONTEND_FILE = BASE_DIR / "site" / "data" / "fund_flow.json"

# ETF 定義：ticker -> 名稱
ETF_DEFINITIONS = {
    "SMH": "VanEck Semiconductor ETF",
    "SOXX": "iShares Semiconductor ETF",
    "SOXQ": "Invesco PHLX Semiconductor ETF",
}

HISTORY_DAYS = 60  # 抓取天數（需要足夠資料算 20 日累計）
OUTPUT_DAYS = 30   # 輸出最近 N 天的 daily_flow


def load_etf_from_stocks() -> dict[str, list[dict]]:
    """嘗試從 stocks.json 讀取 etf_ 開頭的資料"""
    if not STOCKS_FILE.exists():
        return {}

    with open(STOCKS_FILE, "r", encoding="utf-8") as f:
        stocks = json.load(f)

    etf_data = {}
    for key, prices in stocks.items():
        if key.startswith("etf_"):
            ticker = key.replace("etf_", "").upper()
            etf_data[ticker] = prices

    return etf_data


def fetch_etf_from_yfinance(ticker: str, days: int = HISTORY_DAYS) -> list[dict]:
    """用 yfinance 抓取 ETF 歷史資料"""
    try:
        etf = yf.Ticker(ticker)
        hist = etf.history(period=f"{days}d")

        if hist.empty:
            logger.warning(f"  {ticker}: 無資料")
            return []

        prices = []
        for idx, row in hist.iterrows():
            prices.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": round(row["Open"], 2),
                "high": round(row["High"], 2),
                "low": round(row["Low"], 2),
                "close": round(row["Close"], 2),
                "volume": int(row["Volume"]),
            })
        return prices

    except Exception as e:
        logger.warning(f"  {ticker}: 抓取失敗 - {e}")
        return []


def calculate_fund_flow(ticker: str, name: str, prices: list[dict]) -> dict | None:
    """計算單檔 ETF 的資金流向指標"""
    if len(prices) < 2:
        logger.warning(f"  {ticker}: 資料不足（{len(prices)} 天）")
        return None

    # 計算每日 flow: close_change * volume
    daily_flow = []
    for i in range(1, len(prices)):
        prev_close = prices[i - 1]["close"]
        curr = prices[i]
        close_change = curr["close"] - prev_close
        change_pct = round((close_change / prev_close) * 100, 2) if prev_close else 0
        flow = close_change * curr["volume"]

        daily_flow.append({
            "date": curr["date"],
            "flow": round(flow),
            "volume": curr["volume"],
            "change_pct": change_pct,
        })

    if not daily_flow:
        return None

    # 5 日累計 flow
    flow_5d = sum(d["flow"] for d in daily_flow[-5:]) if len(daily_flow) >= 5 else sum(d["flow"] for d in daily_flow)

    # 20 日累計 flow
    flow_20d = sum(d["flow"] for d in daily_flow[-20:]) if len(daily_flow) >= 20 else sum(d["flow"] for d in daily_flow)

    # 趨勢判斷（基於 5 日 flow）
    if flow_5d > 0:
        flow_trend = "inflow"
    elif flow_5d < 0:
        flow_trend = "outflow"
    else:
        flow_trend = "neutral"

    # 最新價格和漲跌幅
    latest = prices[-1]
    latest_change_pct = daily_flow[-1]["change_pct"] if daily_flow else 0

    # 只輸出最近 OUTPUT_DAYS 天
    output_daily = daily_flow[-OUTPUT_DAYS:]

    return {
        "name": name,
        "latest_price": latest["close"],
        "daily_change_pct": latest_change_pct,
        "flow_5d": round(flow_5d),
        "flow_20d": round(flow_20d),
        "flow_trend": flow_trend,
        "daily_flow": output_daily,
    }


def save_json(data: dict, path: Path):
    """存檔 JSON"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"  存檔: {path}")


def main():
    logger.info("=== ETF 資金流向指標 ===\n")

    # 嘗試從 stocks.json 讀取 etf_ 資料
    etf_data = load_etf_from_stocks()

    if etf_data:
        logger.info(f"從 stocks.json 讀取到 {len(etf_data)} 檔 ETF\n")
    else:
        logger.info("stocks.json 無 etf_ 資料，改用 yfinance 抓取\n")

    # 處理每檔 ETF
    results = {}
    for ticker, name in ETF_DEFINITIONS.items():
        logger.info(f"[{ticker}] {name}")

        # 取得價格資料
        if ticker in etf_data:
            prices = etf_data[ticker]
            logger.info(f"  使用 stocks.json 資料（{len(prices)} 天）")
        else:
            prices = fetch_etf_from_yfinance(ticker)
            logger.info(f"  yfinance 抓取到 {len(prices)} 天")

        # 計算 flow
        result = calculate_fund_flow(ticker, name, prices)
        if result:
            results[ticker] = result
            logger.info(f"  flow_5d: {result['flow_5d']:,.0f}")
            logger.info(f"  flow_20d: {result['flow_20d']:,.0f}")
            logger.info(f"  trend: {result['flow_trend']}")
        else:
            logger.warning(f"  跳過（資料不足）")

        print()

    # 輸出
    output = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "etfs": results,
    }

    save_json(output, OUTPUT_FILE)
    save_json(output, FRONTEND_FILE)

    logger.info(f"\n=== 完成 ===")
    logger.info(f"共 {len(results)} 檔 ETF")


if __name__ == "__main__":
    main()
