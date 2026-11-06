# 重現與測試

模型契約缺失時不得啟用DQN/DDQN或修改權重。下列模型檢查只用隔離副本。live runner會重用已完成policy checkpoint；部分policy中斷時明列INTERRUPTED，不用舊choice冒充live，也不自動重複該policy昂貴呼叫。

```powershell
docker compose -f compose.yaml -f compose.ai.yaml up -d
docker compose exec -T backend mkdir -p /app/scripts /tmp/member-review /tmp/ai-comparison
docker compose cp work/ai-comparison/incoming/backend backend:/tmp/member-review/backend
Get-ChildItem scripts/*ai_comparison*.py,scripts/validate_member_models.py,scripts/formal_design.py | ForEach-Object { docker compose cp $_.FullName ("backend:/app/scripts/"+$_.Name) }
docker compose exec -T backend python /app/scripts/validate_member_models.py --source /tmp/member-review/backend --output /tmp/ai-comparison
# feature_contract_check.json須由實際檢查產生並匯入/profiles/ai-comparison；model-validation資料夾亦須匯入
docker compose exec -T backend python /app/scripts/run_ai_comparison.py --plan
docker compose exec -T backend python /app/scripts/run_ai_comparison.py
docker compose exec -T backend python /app/scripts/build_ai_comparison.py
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T backend python /app/scripts/test_ai_comparison.py
node --test frontend/tests/ai-comparison.test.mjs
```

第一次呼叫前已固定24格、10圖順序、參考rho與482次模型呼叫預算。要改情境/模型/圖數需另立版本與輸出，不覆蓋本輪。已有有效輸出請勿刪除重新推論。前端publish/build及實際browser export測試紀錄在tests/，沒有執行的項目會明列NOT VERIFIED。

## 本輪實際執行結果

85後端+4pilot+2服務mock+9前端資料+59browser+63HTTP全通過；來源/權重/20圖hash與先前1282份證據檔hash未改。CPU與link獨立參考最大誤差見tests/test-summary.json。DQN七維/scaler/訓練mapping/正式adapter為BLOCKED或NOT VERIFIED，不計入PASS。

```powershell
node --test frontend/tests/ai-comparison.test.mjs
python scripts/publish_ai_results.py
docker compose build frontend
docker compose up -d --no-deps frontend
node scripts/test_ai_browser.mjs
python scripts/verify_ai_http.py
python scripts/finalize_ai_tests.py
```

Node24內建WebSocket，browser測試用安裝在標準路徑的Edge開獨立headless profile；不接管既有使用者分頁。CSV/JSON必須實際下載並讀回檢查。若環境無此瀏覽器，標NOT VERIFIED，不能沿用本輪PASS冒充新執行。

DQN原始RAR請先tar -tf檢查，再tar -xf解到獨立work/ai-comparison/incoming；不可解到production backend。完整member-original隨本輪交付保留。進行live run前，將模型驗證的feature_contract_check.json與model-validation目錄匯入/profiles/ai-comparison，再固定plan。publish/finalize不會呼叫模型。
