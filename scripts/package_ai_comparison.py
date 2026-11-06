"""Seal an AI pilot delivery without overwriting prior experiments or sources."""
from pathlib import Path
import argparse,json,hashlib,shutil,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'profiles/ai-comparison';W=ROOT/'work/ai-comparison'
a=argparse.ArgumentParser();a.add_argument('--output',required=True,type=Path);args=a.parse_args();out=args.output.resolve();archive=out.with_suffix('.zip')
if out.exists() or archive.exists():raise SystemExit('Existing delivery preserved: choose another output')
assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'Commit before sealing'
v=json.loads((DATA/'validation-summary.json').read_text(encoding='utf-8-sig'));assert v['status_counts']=={'PASS':192,'BLOCKED':48} and v['verified_laya_task_choices']==480
shutil.copytree(DATA,out)
for name in ('AI_COMPARISON_REPORT.md','TEAM_BLOCKERS.md','RUN_TESTS.md','model_validation.md','CODEX_PROGRESS.md'):shutil.copy2(ROOT/name,out/name)
shutil.copytree(W/'incoming/backend',out/'member-original/backend')
shutil.copy2(Path(r'C:\Users\wubai\Downloads\backend.rar'),out/'member-original/backend.rar')
(out/'run-logs').mkdir()
for p in W.iterdir():
 if p.is_file() and p.suffix in ('.log','.json','.txt'):shutil.copy2(p,out/'run-logs'/p.name)
# Preserve reusable profile/model inputs, not photos, DB or InsightFace weights.
formal=ROOT/'profiles/formal-evaluation';ids=json.loads((formal/'profile-ids.json').read_text(encoding='utf-8-sig'));model=json.loads((formal/'evaluation/fit-complete.json').read_text(encoding='utf-8-sig'))['models']['median'];(out/'profiles/estimators').mkdir(parents=True)
for dataset in ('lfw','wider_train'):
 for role in ('training','validation','testing'):
  for suffix in ('.json','.csv'):shutil.copy2(ROOT/'profiles'/(ids[dataset+'/'+role]+suffix),out/'profiles'/(ids[dataset+'/'+role]+suffix))
shutil.copy2(ROOT/'profiles/estimators'/(model+'.json'),out/'profiles/estimators'/(model+'.json'))
shutil.copy2(formal/'plan.json',out/'profiles/formal-frozen-plan.json')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();base=subprocess.check_output(['git','rev-parse','7a38ef7'],cwd=ROOT,text=True).strip();tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode('utf-8').split('\0')
with zipfile.ZipFile(out/'source-snapshot.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name in tracked:
  if name and (ROOT/name).is_file():z.write(ROOT/name,name)
subprocess.run(['git','diff','--binary','--output='+str(out/'changes.patch'),base,head],cwd=ROOT,check=True)
manifest=dict(source_commit=head,baseline_commit=base,member_formal_integration='BLOCKED',reasons='Unknown seven-feature semantics, normalization, training/reward/environment/test split provenance',member_files_sha256=json.loads((DATA/'model-validation/model_validation.json').read_text(encoding='utf-8-sig'))['source_sha256'],scenes=24,count_per_scenario=10,seed=11,deadline_ms=1000,completed_policy_runs=192,blocked_rows=48,completed_task_results=1920,live_laya_task_decisions=480,warmup_calls=2,replay=False,test_summary=json.loads((DATA/'tests/test-summary.json').read_text(encoding='utf-8-sig')),limits='Pilot only; not a trained DQN/DDQN evaluation or pooled ranking. Pure cold model load not measured because service was already loaded. Images, DB, caches, environment secrets and InsightFace/Laya weights excluded; member-provided weights preserved unchanged.')
(out/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'README.md').write_text('''# AI比較交付：已完成共同10圖pilot，DQN/DDQN契約BLOCKED

先讀 [主報告](AI_COMPARISON_REPORT.md)、[組員待補資料](TEAM_BLOCKERS.md)、[模型驗證](model_validation.md)、[重現指令](RUN_TESTS.md)、[進度](CODEX_PROGRESS.md)。

- scenario_manifest.json/task_subset_manifest.json：2資料集×3負載×4網路，固定10圖、seed11、Deadline1000及負載定義；沒有用100圖baseline比較10圖Laya。
- comparison_results.csv：240列，192可用策略PASS及48 DQN/DDQN BLOCKED空值；無虛構性能。
- decision_trace.csv：1920筆任務，input task/node state、real model audit_id、選擇、client/decision/queue/worker時間與事後真值分開。
- raw/runs與raw/scenarios：逐policy/逐情境完整SimPy JSON；raw/decisions：每步checkpoint；raw/model-audit.jsonl：482個真實Laya呼叫（含2預熱），不是Replay。
- charts/{dataset}/{load}/{network}.png：24個獨立情境四合一圖，沒有跨情境總排名。web/為瀏覽器只讀摘要。
- member-original/：使用者提供RAR及六個原始來源/NPZ，未改寫；model-validation/與feature_contract_check.json是獨立數值probe與未知契約證據，不是SimPy正式DQN輸入。
- tests/：85後端、4pilot、2mock、9前端資料、59實際headless Edge、63 HTTP紀錄；含實際下載CSV/JSON、desktop/mobile截圖、已修正測試路徑的初次錯誤及初版圖表。
- profiles/：凍結6份分割CSV/metadata及既有Median註冊模型，僅供重現。照片、DB及大模型cache保留原專案，未重新量測。
- source-snapshot.zip以已提交工作樹原始bytes封存，避免Git autocrlf干擾嚴格run-config hash；changes.patch是從7a38ef7的差異。SHA256SUMS.json覆核所有本包檔案（除它自身）。

頁面：http://localhost:8080/ai-comparison.html。原simulator/人臉辨識仍可用。篩選/指標切換只讀已完成結果，不呼叫模型。模型服務本輪開始已loaded，純首次載入時間未測，預熱排除task cost。

DQN/DDQN weights能執行，不等於特徵/訓練正確。禁止自行從49維選7欄或用規則補AI；待組員提供契約/scaler/environment/reward/splits/golden fixtures後另立正式Adapter與版本。沒有通過DQN gate，因此本輪不擴大30圖，不宣稱已完成DQN與Laya正式公平性能比較。
''',encoding='utf-8')
checks={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()};(out/'SHA256SUMS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.rglob('*')):
  if p.is_file():z.write(p,str(Path(out.name)/p.relative_to(out)))
print(json.dumps(dict(folder=str(out),archive=str(archive),files=len(checks)+1,commit=head,zip_MB=archive.stat().st_size/1e6),ensure_ascii=False))
