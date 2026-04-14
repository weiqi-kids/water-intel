#!/bin/bash
# 啟動本地開發伺服器
# 會自動同步遠端資料再啟動

cd "$(dirname "$0")/.."

echo "=== 同步遠端資料 ==="
git pull origin main 2>/dev/null || echo "（無法同步，使用本地資料）"

echo ""
echo "=== 啟動本地伺服器 ==="
echo "http://localhost:6229"
echo ""
echo "按 Ctrl+C 停止"
echo ""

python3 -m http.server 6229 -d site
