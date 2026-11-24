"""Seal a new delivery directory without altering historical evidence."""
from pathlib import Path
import argparse,shutil,json,hashlib,subprocess,zipfile
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'work/paper-improvements'
a=argparse.ArgumentParser();a.add_argument('--output',required=True,type=Path);args=a.parse_args();out=args.output.resolve()
if out.exists():raise SystemExit('Delivery already exists; choose a new directory')
out.mkdir(parents=True)
reports=['WORKLOAD_ESTIMATOR_EVALUATION.md','LATENCY_AWARE_V2_REPORT.md','LAYA_DECISION_EVALUATION.md','EXPERIMENT_COMPARISON.md','TEAM_INTEGRATION_NOTES.md','CODEX_PROGRESS.md']
for name in reports:shutil.copy2(ROOT/name,out/name)
for path in (W/'results').iterdir():
 if path.is_dir():shutil.copytree(path,out/path.name)
 else:shutil.copy2(path,out/path.name)
for path in W.iterdir():
 if path.is_file() and path.suffix in ('.json','.csv','.log','.txt','.py') and not path.name.startswith(('paper-A','paper-B')):shutil.copy2(path,out/path.name)
for name in ('matrix','api-integration'):shutil.copytree(W/name,out/name)
selection=json.loads((W/'results/estimator-evaluation.json').read_text())
ids=list(selection['test_profile_ids'].values())+['44156f8feb7a49269ec3bc6424b5e176','faef67cd539d44f8b3caea7f58307db8','6ddb0a187ba44065a5beaf0450ad259e','a057ded0f08c4837beff2ffd02f390ee']
(out/'profiles/estimators').mkdir(parents=True)
for identifier in ids:
 for suffix in ('.json','.csv'):
  p=ROOT/'profiles'/(identifier+suffix)
  if p.is_file():shutil.copy2(p,out/'profiles'/p.name)
for identifier in selection['model_ids'].values():shutil.copy2(ROOT/'profiles/estimators'/(identifier+'.json'),out/'profiles/estimators'/(identifier+'.json'))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
subprocess.run(['git','archive','--format=zip','--output='+str(out/'source-snapshot.zip'),head],cwd=ROOT,check=True)
subprocess.run(['git','diff','--binary','--output='+str(out/'changes.patch'),'9739b39',head],cwd=ROOT,check=True)
manifest=dict(source_commit=head,baseline_commit='9739b39d4eee9b8ba0a5a7f9ec79c23b4cf130de',implementation_commit='f312837',backend_tests=77,laya_tests=2,legacy_api_checks=78,new_api_checks=17,matrix=json.loads((W/'matrix-complete.json').read_text()),protected=json.loads((W/'verification-summary.json').read_text())['protected_files'],historical_evidence=json.loads((W/'previous-deliveries-check.json').read_text()),excluded='datasets/images/model weights/cache/database and copyrighted full paper PDFs are not bundled; originals retained')
(out/'delivery-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'README.md').write_text('''# 本輪交付：論文啟發改善與驗證

先讀五份報告與CODEX_PROGRESS.md。原始API格在matrix/，逐seed與彙整為matrix-summary.csv、matrix-aggregate.csv；51筆受控情境及獨立資源日曆在latency-controlled.json；90次診斷與504次矩陣模型raw輸出分開保存。所有不利結果均保留。

models/含7候選，profiles/含兩個registry模型、來源與測試CSV/metadata；split-manifest.json與validation-selection.json記錄凍結分割/選模。source-snapshot.zip是本輪完整Git source，changes.patch是從9739b39的差異。SHA256SUMS.json覆核本交付所有檔案；先前兩包完全未改。

需原專案資料集、Docker volume模型快取才能重新量測/推論，這些不在本ZIP。重現命令見TEAM_INTEGRATION_NOTES與CODEX_PROGRESS。已有矩陣JSON會被驗證並重用；要做全新實驗請另存舊輸出與更換輸出目錄。禁止把本輪資料與不同版本混合，禁止用test重挑模型。原文C/D存取限制如報告；完整論文未重新分發。

判斷：預估器無全面提升證據、V2策略有改善也有退化、Laya兩版數值可靠性未達標。原Median/原策略保留。SimPy/RL受保護四檔未變，回歸全部通過。視覺/點擊UI未測，HTTP與真實辨識/API已測。
''',encoding='utf-8')
checks={str(p.relative_to(out)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out/'SHA256SUMS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
archive=out.with_suffix('.zip')
if archive.exists():raise SystemExit('Archive exists; choose another output')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.rglob('*')):
  if p.is_file():z.write(p,str(Path(out.name)/p.relative_to(out)))
print(json.dumps(dict(folder=str(out),archive=str(archive),files=len(checks)+1,commit=head),ensure_ascii=False))
