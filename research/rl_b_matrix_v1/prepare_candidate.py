"""Seal the accepted Smoke sources and preserve original provenance without edits."""
import hashlib,json,shutil,subprocess,zipfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
SMOKE=BASE.parent/'rl-b-matrix-v1-2026-11-24'
P0=BASE.parent/'p0-contract-portability-2026-11-24'
def sha(b):return hashlib.sha256(b).hexdigest()
def put(p,data):
    with p.open('xb') as f:f.write(data)
if (BASE/'candidate-input.zip').exists():raise SystemExit('Never overwrite a sealed input')
expected={'rl-b-matrix-v1-smoke-evidence.zip':'ac2e17eeab6aa2a393e7a0fb6e2308b34ec37feaf87b081edd759087d36ff184',
          'input.zip':'fd1f763cbf9c60242f216dc0d332e1db2a28cd1442e4927fed085d920bb5d232'}
for name,h in expected.items():assert sha((SMOKE/name).read_bytes())==h
assert sha((P0/'p0-contract-portability-verified.zip').read_bytes())=='48843a3dd32095464e6ef3e4440ac590db7cb2cd22db53037b141492b2870acb'
baseline=json.loads((SMOKE/'baseline.json').read_text(encoding='utf-8'));repo=Path(baseline['original_project'])
for path,h in baseline['original_sha256'].items():assert sha((repo/path).read_bytes())==h,path
assert json.loads((SMOKE/'results/preflight-tests.json').read_text())['tests_run']==130
assert json.loads((SMOKE/'results/smoke/COMPLETE.json').read_text())['training_dispatches']==2400
put(BASE/'accepted-smoke-input.zip',(SMOKE/'input.zip').read_bytes())
put(BASE/'historical-p0-kit.zip',(P0/'p0-contract-portability-verified.zip').read_bytes())
status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain=v1','--untracked-files=all'],encoding='utf-8')
put(BASE/'original-baseline.json',json.dumps(dict(original_project=str(repo),git_status=status,
    original_sha256=baseline['original_sha256'],smoke_artifact_sha256=expected,
    historical_p0_zip_sha256='48843a3dd32095464e6ef3e4440ac590db7cb2cd22db53037b141492b2870acb'),ensure_ascii=False,indent=2).encode())
payload={}
for p in sorted((BASE/'candidate_tools').glob('*.py')):payload['candidate_tools/'+p.name]=p.read_bytes()
payload['CANDIDATE_SOURCE_SHA256.json']=json.dumps({k:sha(v) for k,v in payload.items()},indent=2).encode()
with zipfile.ZipFile(BASE/'candidate-input.zip','x',zipfile.ZIP_DEFLATED) as z:
    for name,blob in payload.items():z.writestr(name,blob)
print(json.dumps(dict(source_files=len(payload)-1,original_files_verified=len(baseline['original_sha256']),
    empty_independent_output=True,free_host_disk_bytes=shutil.disk_usage(BASE).free,
    candidate_input_sha256=sha((BASE/'candidate-input.zip').read_bytes()))),flush=True)
