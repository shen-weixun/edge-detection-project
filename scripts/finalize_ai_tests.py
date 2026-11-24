"""Add final test evidence and conditional interpretations, without recomputing AI."""
from pathlib import Path
import json,csv,hashlib,shutil,re
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'profiles/ai-comparison';W=ROOT/'work/ai-comparison';T=W/'tests'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
expected={'backend-tests.log':85,'pilot-tests.log':4,'laya-service-tests.log':2}
for file,n in expected.items():
 text=(T/file).read_text(encoding='utf-8-sig');assert f'Ran {n} tests' in text and '\nOK' in text,file
assert 'pass 9' in (T/'frontend-unit-tests.log').read_text(encoding='utf-8-sig')
assert read(T/'browser/results.json')['passed']==59 and read(T/'http-results.json')['passed']==63
protected={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in read(W/'protected-baseline.json').items()};assert all(protected.values())
original=ROOT/'work/ai-comparison/incoming/backend';models=read(W/'model-validation/model_validation.json');assert all(hashlib.sha256((original/p).read_bytes()).hexdigest()==sha for p,sha in models['source_sha256'].items())
assert hashlib.sha256(Path(r'C:\Users\wubai\Downloads\backend.rar').read_bytes()).hexdigest()==read(W/'archive-sha256.json')['sha256']
subset=read(O/'task_subset_manifest.json');imagecheck={}
for d,s in subset.items():
 for row in s['images']:assert hashlib.sha256((ROOT/'data'/row['source_path']).read_bytes()).hexdigest()==row['image_sha256']
 imagecheck[d]=len(s['images'])
prior=Path(r'C:\Users\wubai\Documents\Codex\2026-11-04\http-localhost-8080-http-localhost-8080\outputs');old={}
for name in ('simpy-audit','simpy-final-acceptance','paper-inspired-offloading','formal-evaluation'):
 manifest=read(prior/name/'SHA256SUMS.json')
 for file,sha in manifest.items():assert hashlib.sha256((prior/name/file).read_bytes()).hexdigest()==sha,(name,file)
 old[name]=len(manifest)
summary=dict(backend_pass=85,pilot_contract_pass=4,laya_service_mock_pass=2,frontend_data_unit_pass=9,browser_e2e_pass=59,http_pass=63,member_numeric_probes=dict(models=2,probes_per_model=30,repeats_per_probe=20),formal_dqn_adapter='BLOCKED',state_seven_semantics='NOT VERIFIED',training_evidence='NOT VERIFIED',action_mapping_cli='PASS, training mapping NOT VERIFIED',protected_source=protected,member_original_unchanged=True,rar_unchanged=True,subset_image_hashes_verified=imagecheck,previous_evidence_unchanged=old,resource_calendar_max_error_ms=read(O/'validation-summary.json')['reference_max_error_ms'],desktop_mobile_visual='PASS',model_live='480 task calls + 2 warmups, NO REPLAY',pure_first_model_load='NOT SEPARATELY MEASURED: already loaded')
save(T/'test-summary.json',summary);shutil.copytree(T,O/'tests',dirs_exist_ok=True)
rows=list(csv.DictReader((O/'comparison_results.csv').open(encoding='utf-8-sig')));traces=list(csv.DictReader((O/'decision_trace.csv').open(encoding='utf-8-sig')));warm=read(O/'warmup.json')
save(O/'resource-accounting.json',dict(planned_model_calls_including_warmup=482,actual_model_calls_including_warmup=482,task_laya_calls=480,warmup_calls=2,sum_task_client_call_ms=sum(float(r['client_inference_ms']) for r in traces if r['strategy'].startswith('laya')),warmup_total_ms=sum(r['elapsed_ms'] for r in warm['calls']),scope='Budget accounting only, not a pooled performance ranking'))
p=O/'AI_COMPARISON_REPORT.md';text=p.read_text(encoding='utf-8');marker='\n## 最終驗證與Reference條件解讀\n';text=text.split(marker)[0];lines=[marker,'Local配置固定speed1、RTT0、BW1000（不做網路卸載）；四種網路皆為獨立上/下行資源A，不宣稱測試共享出口B。模型服務原已載入，純首次載入時間未測；一致預熱排除統計。','',
'以下每行是獨立的Reference情境，不將資料集/負載混成總排名。CPU決策與單序列排隊會隨到達速度影響端到端；固定Deadline1000ms下，本輪各情境Laya兩版均為0%達成，不能推廣成不同硬體/Deadline必然如此。','',
'|資料集|負載|V1平均ms|Original平均ms|V2平均ms|Original決策等待ms|V2決策等待ms|','|---|---|---|---|---|---|---|']
for d in ('lfw','wider_train'):
 for load in ('Low','Medium','High'):
  x={r['strategy']:r for r in rows if r['dataset']==d and r['load']==load and r['network']=='reference'}
  lines.append('|'+ '|'.join([d,load]+[f"{float(x[k][field]):.3f}" for k,field in [('latency_aware','avg_latency_ms'),('laya','avg_latency_ms'),('laya_v2','avg_latency_ms'),('laya','decision_queue_ms'),('laya_v2','decision_queue_ms')]])+'|')
lines+=['','完整測試實際結果：85/85原後端、4/4 pilot契約、2/2 Laya服務mock、9/9前端資料、59/59真實headless Edge、63/63 HTTP全部通過。真實下載檔與desktop/mobile截圖在tests/browser/；原人臉detect/verify也通過。這不等於DQN正式整合或AI數值選擇品質通過。',
'測試初次pilot腳本缺Python import path，已保存初次錯誤log並修正測試路徑後4/4通過；沒有修改正式runner、policy或放寬驗證。初版雙欄圖表經視覺檢查後改成可讀的單欄，59項browser檢查重跑通過，兩次紀錄保留。']
p.write_text(text+'\n'.join(lines)+'\n',encoding='utf-8')
p=O/'RUN_TESTS.md';text=p.read_text(encoding='utf-8').split('\n## 本輪實際執行結果\n')[0];text+='''
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
''';p.write_text(text,encoding='utf-8')
for name in ('AI_COMPARISON_REPORT.md','TEAM_BLOCKERS.md','RUN_TESTS.md','model_validation.md'):shutil.copy2(O/name,ROOT/name)
print(json.dumps(summary,ensure_ascii=False))
