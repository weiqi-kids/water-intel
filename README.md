# Water Intel

水資源供應鏈情報追蹤。每天自動抓取供應鏈上下游公司的新聞與股價，用規則引擎標記重要性與異常，產出每日與 7 日報告，並在網頁上呈現供應鏈關係圖與事件時間軸。

線上看：<http://water.intel.weiqi.kids/>

## 現在追蹤什麼

- 公司 16 家，分佈在上中下游，設定在 `configs/companies.yml`（含關聯的上下游對象，供應鏈圖就是從這裡長出來的）
- 主題 10 個，每個主題帶一組中英文關鍵字，設定在 `configs/topics.yml`

## 怎麼運作

1. **抓取**：每家公司一個 fetcher（`fetchers/`），新聞走 RSS 或 Playwright，股價走 Yahoo Finance。
2. **規則引擎**：關鍵字比對、情緒判定、重要性評分、異常偵測。規則是 YAML，不是寫死在程式裡（`configs/*_rules.yml`）。
3. **報告**：每日報告與 7 日彙整，輸出到 `reports/daily` 與 `reports/7d`。
4. **前端**：靜態頁面加 D3.js，畫供應鏈圖與事件時間軸，部署到 GitHub Pages。
5. **排程**：GitHub Actions 每天跑一次抓取與重建。

## 技術

Python、Playwright、GitHub Actions、GitHub Pages。規則與追蹤清單全部是設定檔，加一家公司或一個主題不用改程式。

## 這個 repo 的定位

這是 [intel-template](https://github.com/weiqi-kids/intel-template) 的一個實例。要追別的產業就 fork 那個模板，改 `configs/` 就好。

## 免責

自動抓取的公開資訊，僅供研究參考，不是投資建議。情緒與重要性評分是關鍵字規則的結果，不是人工判讀。

---

Maintained by Light. I build and maintain websites with AI as a service: [arthurs.tw](https://arthurs.tw/?utm_source=github&utm_medium=readme&utm_campaign=oss)
