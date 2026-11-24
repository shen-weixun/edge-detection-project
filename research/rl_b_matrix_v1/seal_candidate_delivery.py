"""Read-only audit/export of the finished isolated run. Never trains a model."""
from pathlib import Path,PurePosixPath
import csv,gzip,hashlib,io,json,posixpath,subprocess,zipfile
import numpy as np
BASE=Path(__file__).resolve().parent
def sha(blob):return hashlib.sha256(blob).hexdigest()
def readjson(blob):return json.loads(blob)
baseline=json.loads((BASE/'original-baseline.json').read_text(encoding='utf-8'));repo=Path(baseline['original_project'])
for name,h in baseline['original_sha256'].items():assert sha((repo/name).read_bytes())==h,name
status=subprocess.check_output(['git','-C',str(repo),'status','--porcelain=v1','--untracked-files=all'],encoding='utf-8')
assert status==baseline['git_status']
protection=dict(verdict='PASS',original_files_rechecked=len(baseline['original_sha256']),git_status_unchanged=True,
    original_dqn_ddqn_normalizer_simulator_unchanged=True,original_project_never_mounted=True,
    smoke_zip_sha256=baseline['smoke_artifact_sha256']['rl-b-matrix-v1-smoke-evidence.zip'])
smoke=BASE.parent/'rl-b-matrix-v1-2026-11-24'
for name,h in baseline['smoke_artifact_sha256'].items():assert sha((smoke/name).read_bytes())==h
with (BASE/'original-protection.json').open('x',encoding='utf-8') as f:json.dump(protection,f,indent=2)

run=BASE/'candidate-run.zip'
with zipfile.ZipFile(run) as z:
    manifest=json.loads(z.read('RUN_SHA256.json'))
    for name,h in manifest.items():assert sha(z.read(name))==h,name
    assert z.testzip() is None
    complete=json.loads(z.read('candidate-results/COMPLETE.json'));assert complete['verdict']=='PASS' and complete['training_dispatches']==57600
    checkpoints=json.loads(z.read('candidate-results/checkpoints.json'));assert len(checkpoints)==30
    models={};max_time=max_reward=max_target_error=0.;target_copies=0
    for c in checkpoints:
        path=f'candidate-results/models/{c["algorithm"]}-s{c["seed"]}/checkpoints/{c["step"]:05d}'
        assert sha(z.read(path+'/policy.npz'))==c['sha256']
        assert c['updates']==max(0,c['step']-63) and c['target_updates']==c['updates']//200
        idx=json.loads(z.read(path+'/input-contract-index.json'));assert len(idx['models'])==1
        row=idx['models'][0];docpath=posixpath.normpath(path+'/'+row['contract_path'])
        assert sha(z.read(docpath))==row['contract_sha256']
        doc=json.loads(z.read(docpath));assert doc['input_spec']['feature_mode']=='full' and doc['input_spec']['zeroed_feature_indices']==[]
        root=posixpath.normpath(path+'/'+idx['source_root'])
        for source in doc['sources']:
            src=posixpath.normpath(root+'/'+source['path'])
            assert not src.startswith('../') and sha(z.read(src))==source['sha256'],src
        isolation=json.loads(z.read(path+'/validation-isolation.json'));assert isolation['before']==isolation['after']
        with np.load(io.BytesIO(z.read(path+'/policy.npz')),allow_pickle=False) as p:
            with np.load(io.BytesIO(z.read(path+'/training-state.npz')),allow_pickle=False) as state:
                assert len(state['action'])==c['step'] and state['state'].shape==(c['step'],49)
                for i in range(6):assert np.array_equal(p[f'w{i}'],state[f'online_{i}'])
                assert all(np.isfinite(state[name]).all() for name in state.files)
    # Hashes prove matched external streams; actual states may differ by policy.
    stream_checks={};exploration_checks={};training_tasks=0
    for alg in ['dqn','ddqn']:
        for seed in [42,43,44]:
            key=f'{alg}-s{seed}';folder='candidate-results/models/'+key
            meta=json.loads(z.read(folder+'/training-summary.json'));assert meta['steps']==9600 and meta['updates']==9537
            models[key]=meta;stream_checks[key]=meta['exogenous_stream_sha256']
            epochs=[]
            for ep in range(96):
                obj=json.loads(gzip.decompress(z.read(folder+f'/episodes/e{ep:03d}.json.gz')))
                assert len(obj['transitions'])==100 and len(obj['tasks'])==100
                epochs.append(obj['summary']['random_count']);training_tasks+=100
                max_time=max(max_time,obj['summary']['time_error_ms']);max_reward=max(max_reward,obj['summary']['reward_error'])
            exploration_checks[key]=epochs
            with gzip.GzipFile(fileobj=io.BytesIO(z.read(folder+'/updates.jsonl.gz'))) as f:
                count=0
                for line in f:
                    u=json.loads(line);count+=1;assert u['gradient_update_count']==count
                    max_target_error=max(max_target_error,u['independent_target_error']);target_copies+=int(u['target_synchronized'])
                assert count==9537
    assert training_tasks==57600 and target_copies==282
    for seed in [42,43,44]:
        assert stream_checks[f'dqn-s{seed}']==stream_checks[f'ddqn-s{seed}']
        assert exploration_checks[f'dqn-s{seed}']==exploration_checks[f'ddqn-s{seed}']
    for rel in ['backend/app/offloading/agents49/dqn.py','backend/app/offloading/agents49/ddqn.py','backend/app/offloading/agents49/normalizer.py',
                'backend/app/offloading/agents49/input_contract.py','backend/app/offloading/agents49/integral_env.py','backend/app/offloading/simulator.py',
                'backend/app/offloading/strategies.py','backend/app/offloading/latency_v2.py','backend/app/offloading/rl.py','backend/app/offloading/models.py']:
        before=z.read('runtime/'+rel);after=(repo/rel).read_bytes();assert before==after
        for stage,blob in [('before',before),('after',after)]:
            q=BASE/'source-snapshots'/stage/rel;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(blob)
    verification=dict(verdict='PASS',run_manifest_files=len(manifest),models=6,checkpoints=30,
        historical_contracts_verified=56,source_protected=protection,training_dispatches=57600,
        gradient_updates=57222,target_synchronizations=282,all_checkpoint_sources_and_weights_verified=True,
        all_saved_online_and_replay_shapes_verified=True,all_validation_fingerprints_equal=True,
        matched_dqn_ddqn_external_streams_and_exploration=True,max_reward_error=max_reward,max_time_error_ms=max_time,
        independent_bootstrap_target_error_max=max_target_error,full_validation_dispatches=576000,
        intermediate_validation_dispatches=72000,formal_test=False,A_training=False,Ridge=False,extended14400=False)
    control=json.loads((BASE/'control-validation/summary.json').read_text())
    assert control['verdict']=='PASS' and control['gradient_updates']==0
    control_tasks=0
    for p in (BASE/'control-validation').glob('*.json.gz'):
        control_tasks+=len(json.loads(gzip.decompress(p.read_bytes()))['tasks'])
    assert control_tasks==252
    verification['additional_control_validation_tasks']=control_tasks
    verification['additional_control_gradient_updates']=0
    with (BASE/'FINAL_VERIFICATION.json').open('x',encoding='utf-8') as f:json.dump(verification,f,indent=2)
    # Extract concise reports only; all per-task raw evidence remains in the ZIP.
    report=z.read('candidate-results/reports/B_CANDIDATE_VALIDATION_REPORT.md')
    (BASE/'B_CANDIDATE_VALIDATION_REPORT.md').write_bytes(report)
    (BASE/'CODEX_PROGRESS.md').write_text('''# B candidate progress\n\n2026-11-24: Six B-matrix models completed fixed9600, total57600.\nAll five checkpoints, 240-case full Validation and paired Baselines preserved.\nNo A training, Ridge,14400 extension, formal Test or API integration.\nNo git commit; original dirty working tree unchanged.\nStopped for user review. See B_CANDIDATE_VALIDATION_REPORT.md and FINAL_VERIFICATION.json.\n''',encoding='utf-8')
    (BASE/'REPRODUCE.md').write_text('''# Reproduction and scope\n\nThe original run used existing image sha256:5f866c46ea75f21e9fa98ae0c516f6cd2f7dc4d8bed578db74e1c38048e16530, --network none --read-only --tmpfs /tmp, OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1. Only the new candidate directory was mounted at /delivery. SQLite memory was used; no DB/API/dataset image/model cache mount.\n\nprepare_candidate.py verified the accepted Smoke ZIP/input SHA and all330 original protected files, then sealed candidate-input.zip.\nExecution command: docker run --rm --network none --read-only --tmpfs /tmp --mount "type=bind,source=<NEW_AUTHORIZED_CANDIDATE_DIRECTORY>,target=/delivery" -w /tmp -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 sha256:5f866c46ea75f21e9fa98ae0c516f6cd2f7dc4d8bed578db74e1c38048e16530 python -B /delivery/run_candidate_container.py\n\nExecution is single-use and protected by EXECUTION_RESERVED.json. Do not remove it or rerun this completed authorization. Repeating training requires new authorization and a new directory containing the sealed inputs and unchanged harness.\n\nThe data/profile CSVs are Training and Validation only. Every model was initialized anew; Smoke weights were not resumed. Initial/2400/4800/7200/9600 snapshots are preserved. The final9600 snapshot was evaluated for EVERY seed; no best-model choice.\n\nInside the evidence root, candidate-results/models contains checkpoints and source-bound input-contract-index.json; runtime/,tools/,candidate_tools/,data/,results/design preserve their relative source paths. training-state.npz plus checkpoint.json retain online,target,Replay,RNG/counters for audit; no resume command was executed.\n\nFull raw results are lossless .json.gz, update traces are .jsonl.gz. candidate-results/reports provides unranked stratified CSVs and figures. RUN_SHA256.json verifies the isolated run payload; DELIVERY_SHA256.json verifies this final package.\n\nMidpoint monitor summaries across24 heterogeneous cases are learning diagnostics, not a pooled strategy ranking. Unseen E RTT310 is a small extrapolation beyond Training max300; do not call every unseen case interpolation. Historical hardware/thread provenance and16KB result assumptions remain limitations.\n''',encoding='utf-8')
    extras={name:(BASE/name).read_bytes() for name in ['original-protection.json','FINAL_VERIFICATION.json','B_CANDIDATE_VALIDATION_REPORT.md','B_CANDIDATE_REVIEW_ZH_TW.md','CODEX_PROGRESS.md','REPRODUCE.md']}
    for name in ['prepare_candidate.py','run_candidate_container.py','seal_candidate_delivery.py','original-baseline.json','EXECUTION_RESERVED.json','commands-executed.json','execution-environment.json','progress.log','accepted-smoke-input.zip','candidate-input.zip','historical-p0-kit.zip']:
        extras['reproduction/'+name]=(BASE/name).read_bytes()
    for p in (BASE/'source-snapshots').rglob('*'):
        if p.is_file():extras[p.relative_to(BASE).as_posix()]=p.read_bytes()
    for p in (BASE/'control-validation').glob('*'):
        if p.is_file():extras['post-validation/control-episodes/'+p.name]=p.read_bytes()
    for name in ['validate_control_episodes.py','write_candidate_review.py']:
        extras['post-validation/'+name]=(BASE/name).read_bytes()
    final_manifest={**manifest,'RUN_SHA256.json':sha(z.read('RUN_SHA256.json')),**{k:sha(v) for k,v in extras.items()}}
    final=BASE/'rl-b-matrix-v1-candidate-evidence.zip'
    with zipfile.ZipFile(final,'x',zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as out:
        for name in z.namelist():out.writestr(name,z.read(name))
        for name,blob in extras.items():out.writestr(name,blob)
        out.writestr('DELIVERY_SHA256.json',json.dumps(final_manifest,indent=2).encode())
    with zipfile.ZipFile(final) as out:
        assert out.testzip() is None
        assert len(out.namelist())==len(set(out.namelist()))
        for name,h in final_manifest.items():assert sha(out.read(name))==h
    (BASE/'PACKAGE_SHA256.txt').write_text(sha(final.read_bytes())+'  '+final.name+'\n',encoding='utf-8')
    # A smaller upload/review package retains all policy contract sources but
    # omits full per-task trajectories, TD traces and Replay snapshot arrays.
    quick=BASE/'rl-b-matrix-v1-candidate-review.zip'
    selected=[]
    for name in z.namelist():
        if name.startswith(('runtime/','tools/','candidate_tools/','data/','results/design/','results/event-evidence/','candidate-results/reports/','historical-verification/')):
            selected.append(name)
        elif name.startswith('candidate-results/models/') and '/episodes/' not in name and '/intermediate/' not in name and not name.endswith(('training-state.npz','updates.jsonl.gz')):
            selected.append(name)
        elif name in ['candidate-results/COMPLETE.json','candidate-results/checkpoints.json','candidate-results/training-summary.json','candidate-results/EVALUATION_PLAN.json','candidate-results/preflight/SOURCE_AND_EVENT_GATE_PASS.json','candidate-results/preflight/event-only-summary.json','results/preflight-tests.json','commands-executed.json','execution-environment.json']:
            selected.append(name)
    quick_hashes={name:sha(z.read(name)) for name in selected}
    quick_extra={**extras,'QUICK_REVIEW.md':b'This is the source/summary/policy-weight review subset. Full per-task Validation/Training, raw TD, and Replay snapshot arrays are only in the complete evidence ZIP. All 30 policy input-contract provenance sources are retained. Do not call the subset a full training-resume backup. See QUICK_SHA256.json for the subset manifest.\n'}
    with zipfile.ZipFile(quick,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as q:
        for name in selected:q.writestr(name,z.read(name))
        for name,blob in quick_extra.items():q.writestr(name,blob)
        quick_hashes.update({k:sha(v) for k,v in quick_extra.items()})
        q.writestr('QUICK_SHA256.json',json.dumps(quick_hashes,indent=2).encode())
    with zipfile.ZipFile(quick) as q:
        assert q.testzip() is None
        for name,h in quick_hashes.items():assert sha(q.read(name))==h
        # Every retained policy contract must still be closed within the subset.
        for c in checkpoints:
            path=f'candidate-results/models/{c["algorithm"]}-s{c["seed"]}/checkpoints/{c["step"]:05d}'
            idx=json.loads(q.read(path+'/input-contract-index.json'));d=json.loads(q.read(posixpath.normpath(path+'/'+idx['models'][0]['contract_path'])))
            root=posixpath.normpath(path+'/'+idx['source_root'])
            for src in d['sources']:assert sha(q.read(posixpath.normpath(root+'/'+src['path'])))==src['sha256']
    with (BASE/'PACKAGE_SHA256.txt').open('a',encoding='utf-8') as f:f.write(sha(quick.read_bytes())+'  '+quick.name+'\n')
    print(json.dumps(dict(verdict='PASS',evidence_bytes=final.stat().st_size,evidence_sha256=sha(final.read_bytes()),
        review_bytes=quick.stat().st_size,review_sha256=sha(quick.read_bytes()),verification=verification)),flush=True)
