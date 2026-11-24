"""Single-use isolated execution; original repository is never mounted."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys,time,traceback,zipfile
BASE=Path(__file__).resolve().parent
if (BASE/'EXECUTION_RESERVED.json').exists() or (BASE/'candidate-run.zip').exists():raise SystemExit('Never duplicate an authorized training run')
(BASE/'EXECUTION_RESERVED.json').write_text(json.dumps(dict(training_limit=57600,models=6,per_model=9600)),encoding='utf-8')
ROOT=Path('/tmp/b-candidate');ROOT.mkdir()
def extract(archive,target):
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name in z.namelist():
            p=(target/name).resolve();assert p.is_relative_to(target)
            assert not p.exists();p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
extract(BASE/'accepted-smoke-input.zip',ROOT);extract(BASE/'candidate-input.zip',ROOT)
for manifest in ['INPUT_SHA256.json','CANDIDATE_SOURCE_SHA256.json']:
    for name,h in json.loads((ROOT/manifest).read_text()).items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h
HIST=Path('/tmp/p0-history');HIST.mkdir();extract(BASE/'historical-p0-kit.zip',HIST)
env={**os.environ,'PYTHONPATH':':'.join(map(str,[ROOT/'runtime/backend',ROOT/'runtime/backend/tests',ROOT/'tools',ROOT/'candidate_tools'])),
     'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','DATABASE_URL':'sqlite:///:memory:','PROFILE_ROOT':str(ROOT/'data')}
commands=[];returncode=0;start=time.perf_counter()
def execute(path):
    begin=time.perf_counter();out=[]
    process=subprocess.Popen([sys.executable,'-B',str(path)],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8')
    for line in process.stdout:
        print(line,end='',flush=True);out.append(line)
        with (BASE/'progress.log').open('a',encoding='utf-8') as log:log.write(line)
    code=process.wait();commands.append(dict(script=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else 'historical_p0_verify',exit_code=code,wall_seconds=time.perf_counter()-begin,output=''.join(out)))
    return code
try:
    for script in [HIST/'verify_portability.py',ROOT/'tools/preflight.py',ROOT/'candidate_tools/candidate_preflight.py',ROOT/'candidate_tools/train_candidate.py',ROOT/'candidate_tools/analyze_candidate.py']:
        returncode=execute(script)
        if returncode:break
    (ROOT/'historical-verification').mkdir()
    for p in (HIST/'verification-output').glob('*'):shutil.copyfile(p,ROOT/'historical-verification'/p.name)
except Exception:
    returncode=1;(ROOT/'HARNESS_FAILURE.txt').write_text(traceback.format_exc())
finally:
    (ROOT/'commands-executed.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    integrity={}
    for manifest in ['INPUT_SHA256.json','CANDIDATE_SOURCE_SHA256.json']:
        integrity[manifest]=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in json.loads((ROOT/manifest).read_text()).items())
    assert all(integrity.values()),'Frozen runtime/design source changed'
    (ROOT/'execution-environment.json').write_text(json.dumps(dict(original_project_mounted=False,network='none',root_filesystem='read-only',
        source_integrity=integrity,exit_code=returncode,wall_seconds=time.perf_counter()-start,image_id='sha256:5f866c46ea75f21e9fa98ae0c516f6cd2f7dc4d8bed578db74e1c38048e16530'),indent=2),encoding='utf-8')
    # Export reports separately for immediate reading, and all raw evidence as a
    # single ZIP to avoid thousands of Windows bind-mount file operations.
    export=BASE/'reports';export.mkdir()
    for p in (ROOT/'candidate-results').glob('*'):
        if p.is_file():shutil.copyfile(p,export/p.name)
    if (ROOT/'candidate-results/reports').exists():shutil.copytree(ROOT/'candidate-results/reports',export/'analysis')
    for name in ['commands-executed.json','execution-environment.json']:
        shutil.copyfile(ROOT/name,BASE/name)
    files={}
    for p in sorted(ROOT.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:files[p.relative_to(ROOT).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT/'RUN_SHA256.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    with zipfile.ZipFile(BASE/'candidate-run.zip','x',zipfile.ZIP_STORED,allowZip64=True) as z:
        for p in sorted(ROOT.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:z.write(p,p.relative_to(ROOT).as_posix())
print(json.dumps(dict(exit_code=returncode,evidence_bytes=(BASE/'candidate-run.zip').stat().st_size,wall_seconds=time.perf_counter()-start)),flush=True)
raise SystemExit(returncode)
