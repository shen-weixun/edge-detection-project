"""Create a new formal evidence package; never overwrite previous deliveries."""
from pathlib import Path
import argparse,shutil,json,hashlib,subprocess,zipfile,csv
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'profiles/formal-evaluation';W=ROOT/'work/formal-evaluation'
a=argparse.ArgumentParser();a.add_argument('--output',required=True,type=Path);args=a.parse_args();out=args.output.resolve();archive=out.with_suffix('.zip')
if out.exists() or archive.exists():raise SystemExit('Use a new delivery path; existing output is preserved')
assert json.loads((DATA/'measurement-complete.json').read_text())['successful']==320
assert json.loads((DATA/'evaluation/matrix-complete.json').read_text())['task_results']==345600
assert json.loads((W/'tests/test-summary.json').read_text())['http_checks_pass']==109
assert (DATA/'evaluation/regression-case-study.json').is_file()
shutil.copytree(DATA,out)
for name in ('FORMAL_EXPERIMENT_REPORT.md','WORKLOAD_ESTIMATOR_REPORT.md','LATENCY_AWARE_COMPARISON.md','LAYA_RELIABILITY_REPORT.md','TEAM_INTEGRATION_CONTRACT.md','CODEX_PROGRESS.md'):shutil.copy2(ROOT/name,out/name)
shutil.copytree(W/'tests',out/'tests',dirs_exist_ok=True)
(out/'run-logs').mkdir()
for p in W.iterdir():
 if p.is_file() and p.suffix in ('.log','.txt','.json'):shutil.copy2(p,out/'run-logs'/p.name)
shutil.copy2(W/'docker-build.log',out/'tests/docker-build.log')
plan=json.loads((DATA/'plan.json').read_text());ids=json.loads((DATA/'profile-ids.json').read_text());selected=json.loads((DATA/'evaluation/fit-complete.json').read_text());profileids=set(ids.values())|set(plan['prior_profile_ids'])
(out/'profiles/estimators').mkdir(parents=True)
for identifier in profileids:
 for suffix in ('.json','.csv'):shutil.copy2(ROOT/'profiles'/(identifier+suffix),out/'profiles'/(identifier+suffix))
for identifier in selected['models'].values():shutil.copy2(ROOT/'profiles/estimators'/(identifier+'.json'),out/'profiles/estimators'/(identifier+'.json'))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();baseline=subprocess.check_output(['git','rev-parse','8a80cc5'],cwd=ROOT,text=True).strip()
subprocess.run(['git','archive','--format=zip','--output='+str(out/'source-snapshot.zip'),head],cwd=ROOT,check=True)
subprocess.run(['git','diff','--binary','--output='+str(out/'changes.patch'),baseline,head],cwd=ROOT,check=True)
manifest=dict(commit=head,baseline_commit=baseline,data_seed=20261104,training_images=80,validation_images=40,test_images=200,test_groups=dict(lfw=100,wider_train=16),new_insightface_images=213,insightface_calls=852,reused_real_measurements=107,new_laya_calls=0,matrix_scenarios=432,strategy_runs=3456,formal_task_results=345600,tests=json.loads((W/'tests/test-summary.json').read_text()),model_ids=selected['models'],test_profile_ids={k:v for k,v in ids.items() if k.endswith('testing')},limits='Same declared SimPy assumptions and single measurement host; WIDER event groups are not verified person identities. Real DQN/DDQN models and browser click/visual flows NOT VERIFIED. No copied images, model weights, datasets, DB or secrets bundled.')
(out/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'README.md').write_text('''# 正式實驗交付

先讀 [正式實驗報告](FORMAL_EXPERIMENT_REPORT.md) 的最終八項回答，及 [組員整合契約](TEAM_INTEGRATION_CONTRACT.md)。其餘報告：[估計器](WORKLOAD_ESTIMATOR_REPORT.md)、[V1/V2](LATENCY_AWARE_COMPARISON.md)、[Laya](LAYA_RELIABILITY_REPORT.md)、[完成進度](CODEX_PROGRESS.md)。

- dataset_manifest.json、train_val_test_split.csv：320張實測與群組隔離分割、每圖三次/中位數/人臉數/設備與來源。
- profiles/：六份分割CSV/metadata、重用歷史父Profile、兩個saved模型registry JSON；evaluation/models/保存7候選。
- scenario_matrix.csv、preregistered-design.json：模型選擇與策略評估前凍結的432格；資料split在新增圖片推論前凍結。
- workload_estimator_results.csv、evaluation/estimator_predictions.csv、estimator_subgroups.csv、cross_dataset.csv：所有候選/子群/跨域結果；成對CI是cluster bootstrap。
- strategy_comparison.csv：3456個逐seed結果（每run100圖）；strategy_aggregate.csv保留每條件mean/SD/t95CI；paired_differences.csv分開policy、estimator、combined三種比較，沒有跨負載混排名。
- evaluation/raw/*.json.gz：全部432格原始JSON，僅gzip壓縮，包含workload、task results、events、queue samples與所有策略摘要；可用Python gzip.open(path,'rt',encoding='utf-8')讀取。
- evaluation/independent-validation.json及regression-case-study.json：FCFS/確定性重播與首次相同state下V1/V2分歧的事件診斷；不是免費正式成績。
- laya_diagnostic.csv、laya/：90次既有真實診斷與144筆歷史成本任務；本輪新增Laya推論0，不冒充新100圖模型結果。
- plots/：已視覺核對的scatter、逐條件成對差heatmap與Reference策略圖。tests/與run-logs/：完整回歸與建置/量測/矩陣紀錄。
- team_interface_schema.json、team_contract_example.json：49維可觀測特徵、0/1/2動作、實際DTO範例；沒有真實工作量洩漏。
- source-snapshot.zip、changes.patch、delivery-manifest.json：本輪Git來源與從8a80cc5的完整差異；原核心/V1/RL等10檔未變，先前402份雜湊證據未變。

SHA256SUMS.json涵蓋本交付所有檔案（除它本身）。圖像資料集、DB、權重/模型快取不在交付包，原專案皆保留。重現需要原資料/快取/既有profiles；指令見CODEX_PROGRESS。已完成checkpoint/fit/raw會重用，重跑不會新調參。新研究需使用新版本目錄，不能混入本輪。

可以作為宣告假設下的正式課堂比較證據。不能由此宣稱Ridge/V2普遍勝出、Laya數值可靠、真實遠端平台速度或尚未提供的DQN/DDQN成績。完整限制見報告。
''',encoding='utf-8')
checks={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256SUMS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.rglob('*')):
  if p.is_file():z.write(p,str(Path(out.name)/p.relative_to(out)))
print(json.dumps(dict(folder=str(out),archive=str(archive),files=len(checks)+1,source_commit=head,zip_MB=archive.stat().st_size/1e6),ensure_ascii=False))
