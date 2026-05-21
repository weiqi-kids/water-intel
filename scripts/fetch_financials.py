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


def _safe_int(val):
    """NaN-safe int conversion."""
    if val != val:
        return None
    return int(val)


def _find_row(index, *keywords):
    """精確匹配第一個關鍵字；找不到再依序退而求其次。"""
    for kw in keywords:
        for idx in index:
            if str(idx).lower() == kw:
                return idx
    return None


def _latest_two(bs, row):
    """從欄位由新到舊找到第一個非 nan 當 curr，再往下找下一個非 nan 當 prev。
    回傳 (curr, prev, curr_col_idx)。"""
    curr = prev = None
    curr_idx = None
    cols = bs.columns
    for i in range(len(cols)):
        v = _safe_int(bs.loc[row].iloc[i])
        if v is None:
            continue
        if curr is None:
            curr, curr_idx = v, i
        elif prev is None:
            prev = v
            break
    return curr, prev, curr_idx


def _pct_str(curr, prev):
    if curr is None or prev is None or prev == 0:
        return "N/A"
    return f"{(curr - prev) / abs(prev) * 100:+.0f}%"


def fetch_company_financials(ticker: str, inventory_applicable: bool = True) -> dict | None:
    """抓取單一公司的 AR 和 Inventory 數據。

    嘗試順序：
    1. quarterly_balance_sheet → QoQ
    2. 若 QoQ 無法計算（curr 或 prev 為 nan），退回 balance_sheet（年報）→ YoY
       — 應付如 Bridgestone 這類 yfinance 季表只有 1 季有效資料的情況

    inventory_applicable=False 時完全跳過 Inv（適用 SaaS／REIT／勘探商等本來就無庫存的公司）。
    """
    try:
        t = yf.Ticker(ticker)
        bs_q = t.quarterly_balance_sheet
        if bs_q is None or bs_q.empty:
            return None

        ar_row_q = _find_row(bs_q.index, "accounts receivable", "receivables")
        inv_row_q = _find_row(bs_q.index, "inventory") if inventory_applicable else None

        if ar_row_q is None and inv_row_q is None:
            return None

        # 年報 lazy load
        bs_a = None
        def get_annual():
            nonlocal bs_a
            if bs_a is None:
                try:
                    bs_a = t.balance_sheet
                except Exception:
                    bs_a = False  # 標記嘗試過但失敗
            return bs_a if bs_a is not False else None

        result = {}
        rep_q_idx = None  # 用來組 quarter_date：選 AR/Inv 中最新的季

        # ---- AR ----
        if ar_row_q is not None:
            ar_curr, ar_prev, ar_q_idx = _latest_two(bs_q, ar_row_q)
            ar_qoq = _pct_str(ar_curr, ar_prev)
            ar_period = "QoQ"
            ar_date = bs_q.columns[ar_q_idx].strftime("%Y-%m-%d") if ar_q_idx is not None else None
            if ar_qoq == "N/A":
                ann = get_annual()
                if ann is not None and not ann.empty:
                    ar_row_a = _find_row(ann.index, "accounts receivable", "receivables")
                    if ar_row_a is not None:
                        a_curr, a_prev, a_idx = _latest_two(ann, ar_row_a)
                        a_qoq = _pct_str(a_curr, a_prev)
                        if a_qoq != "N/A":
                            ar_curr, ar_prev, ar_qoq = a_curr, a_prev, a_qoq
                            ar_period = "YoY"
                            ar_date = ann.columns[a_idx].strftime("%Y-%m-%d")
            else:
                rep_q_idx = ar_q_idx if rep_q_idx is None else min(rep_q_idx, ar_q_idx)
            result.update(ar=ar_curr, ar_prev=ar_prev, ar_qoq=ar_qoq, ar_period=ar_period, ar_date=ar_date)

        # ---- Inv ----
        if inv_row_q is not None:
            inv_curr, inv_prev, inv_q_idx = _latest_two(bs_q, inv_row_q)
            inv_qoq = _pct_str(inv_curr, inv_prev)
            inv_period = "QoQ"
            inv_date = bs_q.columns[inv_q_idx].strftime("%Y-%m-%d") if inv_q_idx is not None else None
            if inv_qoq == "N/A":
                ann = get_annual()
                if ann is not None and not ann.empty:
                    inv_row_a = _find_row(ann.index, "inventory")
                    if inv_row_a is not None:
                        a_curr, a_prev, a_idx = _latest_two(ann, inv_row_a)
                        a_qoq = _pct_str(a_curr, a_prev)
                        if a_qoq != "N/A":
                            inv_curr, inv_prev, inv_qoq = a_curr, a_prev, a_qoq
                            inv_period = "YoY"
                            inv_date = ann.columns[a_idx].strftime("%Y-%m-%d")
            else:
                rep_q_idx = inv_q_idx if rep_q_idx is None else min(rep_q_idx, inv_q_idx)
            result.update(inventory=inv_curr, inv_prev=inv_prev, inv_qoq=inv_qoq, inv_period=inv_period, inv_date=inv_date)

        # quarter_date：優先 quarterly 的最新一季；都沒有時用 AR/Inv 的 fallback 日期之較新者
        if rep_q_idx is not None:
            quarter_date = bs_q.columns[rep_q_idx].strftime("%Y-%m-%d")
        else:
            dates = [d for d in (result.get("ar_date"), result.get("inv_date")) if d]
            quarter_date = max(dates) if dates else None
        if quarter_date is None:
            return None
        result["quarter_date"] = quarter_date

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

        inventory_applicable = company.get("inventory_applicable", True)

        print(f"Fetching {cid} ({ticker})...")
        data = fetch_company_financials(ticker, inventory_applicable=inventory_applicable)

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
                "ar_period": data.get("ar_period", "QoQ"),
                "inventory": data.get("inventory"),
                "inv_prev": data.get("inv_prev"),
                "inv_qoq": data.get("inv_qoq", "N/A"),
                "inv_period": data.get("inv_period", "QoQ"),
                "inventory_applicable": inventory_applicable,
                "alert": alert,
                "quarter_date": data["quarter_date"],
            }
            results.append(entry)
            ar_qoq = data.get('ar_qoq', 'N/A')
            ar_label = f"{ar_qoq}({data.get('ar_period', 'QoQ')})" if ar_qoq != 'N/A' else 'N/A'
            if not inventory_applicable:
                inv_label = '—'
            else:
                inv_qoq = data.get('inv_qoq', 'N/A')
                inv_label = f"{inv_qoq}({data.get('inv_period', 'QoQ')})" if inv_qoq != 'N/A' else 'N/A'
            print(f"  AR: {ar_label}, Inv: {inv_label}")
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
