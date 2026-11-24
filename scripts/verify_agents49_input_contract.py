"""Verify P0-01 with sealed training observations. No env episodes, train_step or Test data."""
import argparse
from copy import deepcopy
import csv
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import traceback

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backend'))
from app.offloading.agents49.adapter import load_agent, Agent49Policy
from app.offloading.agents49.evaluation import evaluation_snapshot
from app.offloading.agents49.input_contract import file_sha256
from app.offloading.models import DecisionTask, NodeState, SystemState
from rl_long_horizon_study import Policy as ValidationPolicy

ATOL = 1e-12
RTOL = 1e-12


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def reference_normalized(raw, dropped, features):
    """Scalar math.log1p from the original member manifest, independent of runtime helpers."""
    masked=raw.copy();masked[:,dropped]=0
    return masked,np.array([[float(x) if f['binary'] else math.log1p(float(x)/f['scale'])
                              for x,f in zip(row,features)] for row in masked],dtype=np.float64)


def reference_q(normalized, checkpoint):
    """Direct NPZ tensors and einsum, independent of Agent._forward/matmul implementation."""
    x=normalized.copy()
    with np.load(checkpoint,allow_pickle=False) as weights:
        for layer in range(3):
            x=np.einsum('ni,ij->nj',x,weights[f'w{2*layer}'],optimize=False)+weights[f'w{2*layer+1}']
            if layer<2:x=np.maximum(x,0)
    if not np.isfinite(x).all():raise AssertionError('Reference Q is nonfinite')
    return x


def observation(raw, task_id):
    task=DecisionTask(task_id,*raw[:7])
    nodes={name:NodeState(name,*raw[7+14*i:7+14*(i+1)]) for i,name in enumerate(('local','edge','cloud'))}
    return task,SystemState(**nodes)


def audit(repo,baseline,contracts,out):
    repo,baseline,contracts,out=map(lambda p:Path(p).resolve(),(repo,baseline,contracts,out))
    if out.exists():raise ValueError('Choose a new verification output')
    out.mkdir(parents=True);(out/'golden').mkdir()
    runtime_files=['backend/app/offloading/agents49/'+n+'.py' for n in
                   ('input_contract','dqn','ddqn','adapter','normalizer','evaluation')]
    runtime_files+=['scripts/rl_long_horizon_study.py','scripts/rl_method_study.py',
                    'scripts/verify_agents49_input_contract.py']
    runtime_sha={name:file_sha256(repo/name) for name in runtime_files}
    inventory=read(contracts/'inventory.json');index=contracts/'index.json'
    observations=repo/'profiles/rl-method-v1/training-observations.npz'
    before=read(baseline/'baseline.json')['files']
    assert file_sha256(observations)==before['profiles/rl-method-v1/training-observations.npz']['sha256']
    with np.load(observations,allow_pickle=False) as data:raw=data['raw'].copy()
    assert raw.shape==(960,49) and np.isfinite(raw).all()
    features=read(repo/'work/agents49/incoming/SimPy49_DQN_DDQN_New/examples/feature_names.json')['features']
    original=baseline/'source-before/backend/app/offloading/agents49/dqn.py'
    assert file_sha256(original)==before['backend/app/offloading/agents49/dqn.py']['sha256']
    spec=importlib.util.spec_from_file_location('app.offloading.agents49._p0_original_dqn',original)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    reports=[]
    for model in inventory:
        checkpoint=repo/model['checkpoint'];algorithm=model['algorithm'];sha=model['checkpoint_sha256']
        assert file_sha256(checkpoint)==sha
        training=load_agent(algorithm,checkpoint,sha,contract_index=index)
        validation=ValidationPolicy(evaluation_snapshot(training,991))
        adapter=Agent49Policy(load_agent(algorithm,checkpoint,sha,contract_index=index))
        expected_masked,expected_norm=reference_normalized(raw,model['mask'],features)
        expected_q=reference_q(expected_norm,checkpoint)
        allowed=np.array([[i for i,j in enumerate((14,28,42)) if r[j]==1] for r in raw])
        assert allowed.shape==(960,3)  # Artificial unavailable cases are separately covered by unit tests.
        expected_actions=expected_q.argmax(axis=1)
        _,unmasked_norm=reference_normalized(raw,[],features)
        unmasked_q=reference_q(unmasked_norm,checkpoint)
        original_full=module.DQN()
        if model['feature_mode']=='full':original_full.load(checkpoint)
        rng_before=deepcopy(training.rng.bit_generator.state)
        trace={};old_prepare=training.prepare_state;old_forward=training._forward
        def capture_prepare(values):
            prepared=old_prepare(values);trace['prepared']=prepared;return prepared
        def capture_forward(x,weights):
            result=old_forward(x,weights);trace['network_input']=x[0].copy();trace['q']=result[2][0].copy();return result
        training.prepare_state=capture_prepare;training._forward=capture_forward
        paths={name:{field:[] for field in ('masked','normalized','q','action')} for name in ('training','validation','adapter')}
        replay_current=[];replay_next=[];replay_available=[];full_before_actions=[];max_error=0.
        for i,row in enumerate(raw):
            action=training.act(row,epsilon=0)
            prepared=trace['prepared'];q=trace['q']
            np.testing.assert_array_equal(trace['network_input'],prepared.normalized)
            obs=observation(row,i)
            validation.select_node(*obs);adapter.select_node(*obs)
            records={
                'training':dict(masked=prepared.masked,normalized=prepared.normalized,q=q,action=action),
                'validation':dict(masked=validation.policy.decisions[-1]['masked_features'],
                                  normalized=validation.policy.decisions[-1]['normalized_features'],
                                  q=validation.policy.decisions[-1]['q_values'],action=validation.policy.decisions[-1]['action']),
                'adapter':dict(masked=adapter.decisions[-1]['masked_features'],
                               normalized=adapter.decisions[-1]['normalized_features'],
                               q=adapter.decisions[-1]['q_values'],action=adapter.decisions[-1]['action'])}
            for name,record in records.items():
                np.testing.assert_array_equal(record['masked'],expected_masked[i],err_msg=f'{model["name"]}/{i}/{name}/mask')
                np.testing.assert_allclose(record['normalized'],expected_norm[i],atol=ATOL,rtol=RTOL)
                np.testing.assert_allclose(record['q'],expected_q[i],atol=ATOL,rtol=RTOL)
                assert record['action']==int(expected_actions[i]),(model['name'],i,name,'Action mismatch')
                max_error=max(max_error,float(np.max(np.abs(np.array(record['q'])-expected_q[i]))))
                for field in record:paths[name][field].append(record[field])
            # Production paths must be exactly equal, not merely within reference tolerance.
            for name in ('validation','adapter'):
                for field in ('masked','normalized','q'):
                    np.testing.assert_array_equal(records['training'][field],records[name][field])
            assert prepared.available_actions==tuple(allowed[i])
            assert adapter.decisions[-1]['available_actions']==allowed[i].tolist()
            j=(i+1)%len(raw);done=bool(i%2)
            training.remember(row,action,-.125,raw[j],done)
            current,a,r,nxt,d,next_mask=training.memory[-1]
            np.testing.assert_allclose(current,expected_norm[i],atol=ATOL,rtol=RTOL)
            np.testing.assert_allclose(nxt,expected_norm[j],atol=ATOL,rtol=RTOL)
            np.testing.assert_array_equal(next_mask,[1,1,1])
            assert (a,r,d)==(action,-.125,done)
            replay_current.append(current);replay_next.append(nxt);replay_available.append(next_mask)
            training.memory.clear()
            if model['feature_mode']=='full':
                previous=original_full.act(row,epsilon=0);assert previous==action;full_before_actions.append(previous)
        assert rng_before==training.rng.bit_generator.state
        assert training.updates==0 and not training.memory
        assert file_sha256(checkpoint)==sha
        arrays=dict(expected_masked=expected_masked,expected_normalized=expected_norm,expected_q=expected_q,
                    expected_action=expected_actions,replay_current=np.array(replay_current),
                    replay_next=np.array(replay_next),replay_available=np.array(replay_available),
                    full_before_actions=np.array(full_before_actions))
        for name,records in paths.items():
            for field,values in records.items():arrays[name+'_'+field]=np.asarray(values)
        np.savez_compressed(out/'golden'/f'{model["name"]}.npz',**arrays)
        report={k:model[k] for k in ('name','suite','algorithm','feature_mode','checkpoint_sha256','contract_sha256')}
        report.update(status='PASS',observations=960,three_path_action_mismatches=0,mask_mismatches=0,
                      replay_mismatches=0,max_q_reference_abs_error=max_error,
                      pre_fix_unmasked_action_differences=int(np.count_nonzero(unmasked_q.argmax(axis=1)!=expected_actions)),
                      full_pre_fix_action_mismatches=0 if model['feature_mode']=='full' else None,
                      training_updates=training.updates)
        reports.append(report)
        print(model['name'],'PASS',flush=True)
    # Existing published synthetic Golden Fixtures, without instantiating Study or reading Test profiles.
    fixtures=read(repo/'profiles/agents49/DQN_DDQN_GOLDEN_FIXTURES.json')['fixtures'];golden=[]
    by_sha={(m['algorithm'],m['checkpoint_sha256']):m for m in inventory}
    for i,fixture in enumerate(fixtures):
        for name,expected in fixture['models'].items():
            algorithm=name.split('_')[0];model=by_sha[algorithm,expected['checkpoint_sha256']]
            checkpoint=repo/model['checkpoint'];agent=load_agent(algorithm,checkpoint,model['checkpoint_sha256'],contract_index=index)
            p,q,action=agent.predict_greedy(fixture['raw_features'])
            np.testing.assert_allclose(p.normalized,fixture['normalized_features'],atol=ATOL,rtol=RTOL)
            np.testing.assert_allclose(q,expected['q_values'],atol=ATOL,rtol=RTOL)
            assert action==expected['action']
            golden.append(dict(fixture=i,model=name,status='PASS',max_q_abs_error=float(np.max(np.abs(q-expected['q_values'])))))
    long=[r for r in reports if r['suite']=='long-horizon'];pruned=[r for r in long if r['feature_mode']=='pruned']
    assert len(long)==48 and len(pruned)==24 and len(reports)==56
    assert runtime_sha=={name:file_sha256(repo/name) for name in runtime_files}
    summary=dict(status='PASS',rtol=RTOL,atol=ATOL,python=platform.python_version(),numpy=np.__version__,
                 training_observations_sha256=file_sha256(observations),contract_index_sha256=file_sha256(index),
                 models=56,long_horizon_models=48,pruned_models=24,full_long_horizon_models=24,
                 historical_full_models=8,model_state_cases=len(reports)*960,long_horizon_cases=48*960,
                 production_routes=3,three_path_action_mismatches=0,mask_mismatches=0,replay_mismatches=0,
                 pre_fix_pruned_models_with_action_differences=sum(r['pre_fix_unmasked_action_differences']>0 for r in pruned),
                 max_q_reference_abs_error=max(r['max_q_reference_abs_error'] for r in reports),
                 historical_golden_cases=len(golden),training_updates=0,formal_test_runs=0,
                 runtime_source_sha256=runtime_sha,
                 note='Independent scalar normalization and einsum from original NPZ; actual act/replay/validation/adapter exercised.')
    (out/'models.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    with (out/'models.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(reports[0]));writer.writeheader();writer.writerows(reports)
    (out/'historical-golden.json').write_text(json.dumps(golden,indent=2),encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('repo','baseline','contracts','out'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    try:audit(args.repo,args.baseline,args.contracts,args.out)
    except Exception:
        if args.out.exists():(args.out/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
