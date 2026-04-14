# Water Intel - 水資源供應鏈情報追蹤

## 專案狀態：建置中

### 系統架構

| 模組 | 說明 | 狀態 |
|------|------|------|
| **股價抓取** | 14 檔股票 + 2 檔 ETF，Yahoo Finance | 待建置 |
| **新聞爬蟲** | 涵蓋 14 家公司 | 待建置 |
| **規則引擎** | 關鍵字匹配、情緒分析、重要性評分、異常偵測 | 待客製化 |
| **報告生成** | 每日報告、7 日報告 | 待建置 |
| **前端** | D3.js Dashboard、供應鏈圖、事件時間軸 | 待建置 |
| **CI/CD** | daily-ingest.yml + deploy-pages.yml | 待建置 |

---

## 追蹤範圍

### 公司 (14 家)

**上游 - 設備/零組件** (3 家)
- Mueller Water Products 穆勒 (MWA NYSE) - 管材設備
- Energy Recovery (ERII NASDAQ) - 能量回收設備
- 千附精密 (6235.TWO TPEx) - 水處理零組件

**中游 - 水處理/水務** (9 家)
- Xylem 賽萊默 (XYL NYSE) - 水處理設備
- Veolia 威立雅 (VIE.PA Euronext) - 水務營運
- Pentair 濱特爾 (PNR NYSE) - 水處理設備
- A.O. Smith 史密斯 (AOS NYSE) - 熱水器/淨水器
- Danaher 丹納赫 (DHR NYSE) - 水質分析
- Watts (WTS NYSE) - 流量控制
- Badger Meter 巴傑 (BMI NYSE) - 智慧水表
- Kurita 栗田 (6370.T TSE) - 水處理化學品
- 中宇環保 (1535.TW TWSE) - 水處理工程

**下游 - 公用事業** (2 家)
- Essential Utilities 必要公用 (WTRG NYSE)
- American Water Works 美國水務 (AWK NYSE)

### ETF (2 檔)
- PHO - Invesco Water Resources ETF
- CGW - Invesco S&P Global Water Index ETF

### 主題 (configs/topics.yml)

- 水資源短缺 (water_scarcity)
- 海水淡化 (desalination)
- 廢水處理 (wastewater_treatment)
- 半導體超純水 (semiconductor_ultrapure_water)
- 智慧水務 (smart_water)
- 財報 / 展望
- 資本支出
- 法規

---

## 標準流程

```
fetch_news → enrich_event → generate_metrics → detect_anomalies →
generate_daily → generate_7d_report → update_baselines → deploy
```

## 資料夾結構

```
water-intel/
├── lib/                        # 規則引擎
├── scripts/                    # 執行腳本
├── configs/                    # 設定檔
│   ├── companies.yml           # 14 家公司 + 上下游關係
│   ├── topics.yml              # 主題 + 關鍵字
│   ├── sentiment_rules.yml     # 情緒詞典
│   ├── importance_rules.yml    # 重要性規則
│   └── anomaly_rules.yml       # 異常偵測規則
├── fetchers/                   # 公司新聞爬蟲
├── data/
│   ├── raw/                    # 原始抓取資料
│   ├── events/                 # 標準格式事件 (JSONL)
│   ├── metrics/                # 每日指標
│   ├── baselines/              # 歷史基準線
│   ├── normalized/             # 股價資料
│   ├── financials/             # 財務資料
│   ├── holders/                # 持股資料
│   └── fund_flow/              # 資金流向
├── reports/
│   ├── daily/                  # 每日報告
│   └── 7d/                     # 7 日報告
├── site/
│   ├── index.html              # D3.js Dashboard
│   └── data/                   # 前端資料
└── CLAUDE.md
```

---

## 產出報告（Claude CLI）

當用戶說「產出報告」時，執行以下流程：

### 1. 拉取最新資料
```bash
git pull origin main
```

### 2. 讀取事件資料
- 讀取近 7 天的 `data/events/{date}.jsonl`
- 識別重要事件、主題趨勢、供應鏈動態

### 3. 產出分析並寫入 JSON
讀取現有的 Actions 報告 JSON，追加 `llm_analysis` 和 `financials` 欄位。

### 4. Commit 並 Push
```bash
git add site/data/reports/
git commit -m "Weekly report: {date}"
git push
```

---

## 快速啟動

```bash
cd repos/water-intel
source .venv/bin/activate

# 啟動本地伺服器
python3 -m http.server 6230 -d site

# 瀏覽器開啟
open http://localhost:6230
```
