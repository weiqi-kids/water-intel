#!/usr/bin/env python3
"""
抓取追蹤公司的季度財務數據（應收帳款、庫存）

從 configs/companies.yml 讀取 ticker，用 yfinance 抓取 quarterly_balance_sheet，
計算 QoQ 變化百分比，輸出到 data/financials/latest.json 和 site/data/financials.json。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed, skipping financial data fetch")
    sys.exit(0)


def fetch_company_financials(ticker: str) -> dict | None:
    """抓取單一公司的 AR 和 Inventory 數據"""
    try:
        t = yf.Ticker(ticker)
        bs = t.quarterly_balance_sheet
        if bs is None or bs.empty:
            return None

        # 找 Accounts Receivable 和 Inventory
        ar_row = None
        inv_row = None
        for idx in bs.index:
            s = str(idx).lower()
            if s == "accounts receivable":
                ar_row = idx
            elif s == "inventory":
                inv_row = idx

        if ar_row is None and inv_row is None:
            return None

        # 取最近兩季
        cols = bs.columns
        if len(cols) < 2:
            return None

        quarter_date = cols[0].strftime("%Y-%m-%d")

        def safe_int(val):
            if val != val:  # NaN check
                return None
            return int(val)

        result = {"quarter_date": quarter_date}

        if ar_row is not None:
            ar_curr = safe_int(bs.loc[ar_row].iloc[0])
            ar_prev = safe_int(bs.loc[ar_row].iloc[1])
            result["ar"] = ar_curr
            result["ar_prev"] = ar_prev
            if ar_curr is not None and ar_prev is not None and ar_prev != 0:
                pct = (ar_curr - ar_prev) / abs(ar_prev) * 100
                result["ar_qoq"] = f"{pct:+.0f}%"
            else:
                result["ar_qoq"] = "N/A"

        if inv_row is not None:
            inv_curr = safe_int(bs.loc[inv_row].iloc[0])
            inv_prev = safe_int(bs.loc[inv_row].iloc[1])
            result["inventory"] = inv_curr
            result["inv_prev"] = inv_prev
            if inv_curr is not None and inv_prev is not None and inv_prev != 0:
                pct = (inv_curr - inv_prev) / abs(inv_prev) * 100
                result["inv_qoq"] = f"{pct:+.0f}%"
            else:
                result["inv_qoq"] = "N/A"

        return result

    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None


def main():
    # 讀取公司設定
    config_path = Path(__file__).parent.parent / "configs" / "companies.yml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    companies = config.get("companies", [])
    results = []
    quarter_dates = set()

    for company in companies:
        ticker = company.get("ticker")
        if not ticker:
            continue

        cid = company["id"]
        name = company["name"]
        currency = company.get("currency", "USD")

        # 找中文 short_name
        import re
        aliases = company.get("aliases") or []
        short_name = name
        for a in aliases:
            if a and re.search(r"[\u4e00-\u9fff]", a):
                short_name = a
                break

        print(f"Fetching {cid} ({ticker})...")
        data = fetch_company_financials(ticker)

        if data:
            quarter_dates.add(data["quarter_date"])

            # 判斷是否需要 alert（AR 或庫存 QoQ > ±20%）
            alert = False
            for key in ["ar_qoq", "inv_qoq"]:
                qoq = data.get(key, "N/A")
                if qoq != "N/A":
                    try:
                        val = float(qoq.replace("%", "").replace("+", ""))
                        if abs(val) > 20:
                            alert = True
                    except ValueError:
                        pass

            entry = {
                "id": cid,
                "name": short_name,
                "ticker": ticker,
                "currency": currency,
                "ar": data.get("ar"),
                "ar_prev": data.get("ar_prev"),
                "ar_qoq": data.get("ar_qoq", "N/A"),
                "inventory": data.get("inventory"),
                "inv_prev": data.get("inv_prev"),
                "inv_qoq": data.get("inv_qoq", "N/A"),
                "alert": alert,
                "quarter_date": data["quarter_date"],
            }
            results.append(entry)
            print(f"  AR: {data.get('ar_qoq', 'N/A')}, Inv: {data.get('inv_qoq', 'N/A')}")
        else:
            print(f"  No data")

    # 組裝輸出
    quarter_label = ", ".join(sorted(quarter_dates)[:3]) if quarter_dates else "N/A"
    output = {
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "quarter": quarter_label,
        "companies": sorted(results, key=lambda x: x["id"]),
    }

    # 輸出到 data/financials/
    data_dir = Path(__file__).parent.parent / "data" / "financials"
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "latest.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {data_path}")

    # 同步到 site/data/
    site_path = Path(__file__).parent.parent / "site" / "data" / "financials.json"
    with open(site_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"Saved to {site_path}")

    print(f"\nTotal: {len(results)} companies with financial data")


if __name__ == "__main__":
    main()
