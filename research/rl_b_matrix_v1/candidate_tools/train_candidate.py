"""Six fixed B candidates only. No tuning, early best-seed selection, or Test."""
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from statistics import mean
import gzip,json,random,time,traceback
import numpy as np
from common import ROOT,canonical,digest,file_sha,write,rng_state
from design import config,load_data,SEEDS
from diagnostics import AGENTS
from evidence import AuditedIntegralEnv,conservation,adaptation
from app.offloading.models import Task
from app.offloading.integration_contract import feature_vector
from app.offloading.experiment import metrics
from app.offloading.agents49.adapter import load_agent
from app.offloading.agents49.input_contract import InputSpec,export_agent_contract,write_contract_index
from candidate_common import OUT,CHECKPOINTS,LIMIT,gzwrite,weights_sha,fingerprint,resource_guard,all_finite,audit_bootstrap
from candidate_evaluation import intermediate_cases,evaluate_case

def save_resume(agent,path):
    m=list(agent.memory);n=len(m)
    payload={**{f'online_{i}':w for i,w in enumerate(agent.online)},**{f'target_{i}':w for i,w in enumerate(agent.target)},
        'state':np.stack([r[0] for r in m]) if n else np.empty((0,49)),
        'action':np.array([r[1] for r in m],dtype=np.int64),'reward':np.array([r[2] for r in m]),
        'next_state':np.stack([r[3] for r in m]) if n else np.empty((0,49)),
        'done':np.array([r[4] for r in m],dtype=bool),'mask':np.stack([r[5] for r in m]) if n else np.empty((0,3))}
    np.savez_compressed(path,**payload)

def probe_model(agent):
    cases=json.loads((ROOT/'results/event-evidence/event-reversals.json').read_text())
    out=[]
    for name,c in cases.items():
        raw=c['observation']['features'];_,q,action=agent.predict_greedy(raw);all_finite(q)
        out.append(dict(case=name,q_values=q.tolist(),action=int(action),node=('local','edge','cloud')[action],
            observable_estimated_best=c['observation']['V2'],raw_features=raw,
            source='actual SimPy observation; not an optimal-action label'))
    return out

def checkpoint(agent,seed,step,episodes,update_stats,intermediate,estimator):
    folder=OUT/f'models/{agent.algorithm}-s{seed}/checkpoints/{step:05d}';folder.mkdir(parents=True)
    before=fingerprint(agent);weight=folder/'policy.npz';agent.save(weight)
    meta=dict(algorithm=agent.algorithm,seed=seed,step=step,updates=agent.updates,target_updates=agent.updates//200,
        sha256=file_sha(weight),objective='integral',gamma=1,feature_mask=[],role='B_CANDIDATE_VALIDATION_ONLY_NOT_TESTED',
        hyperparameters=dict(lr=.0003,batch=64,replay=50000,target_interval=200,episode_tasks=100,deadline_ms=1000),
        rng_state=agent.rng.bit_generator.state,training_state_fingerprint=before)
    write(folder/'checkpoint.json',meta);save_resume(agent,folder/'training-state.npz')
    sources=[folder/'checkpoint.json',ROOT/'results/design/training-manifest.json',ROOT/'results/design/validation-manifest.json',ROOT/'data/estimator.json',
        *sorted((ROOT/'candidate_tools').glob('*.py')),*[ROOT/'tools'/p for p in ('design.py','diagnostics.py','evidence.py')],
        *[ROOT/'runtime/backend/app/offloading/agents49'/p for p in ('dqn.py','ddqn.py','input_contract.py','normalizer.py','integral_env.py')]]
    ref=export_agent_contract(agent,weight,folder/'input-contracts',sources);write_contract_index(folder/'input-contract-index.json',[ref])
    frozen=load_agent(agent.algorithm,weight,meta['sha256'],contract_index=folder/'input-contract-index.json');frozen.gamma=1
    assert all(np.array_equal(a,b) for a,b in zip(agent.online,frozen.online))
    diagnostics=[]
    for i,case in enumerate(intermediate):
        result=evaluate_case(case,estimator,False,agent=frozen,checkpoint=meta)
        gzwrite(folder/f'intermediate/v{i:02d}.json.gz',result);diagnostics.append(result['summary'])
    probes=probe_model(frozen);write(folder/'queue-probes.json',probes)
    after=fingerprint(agent);assert before==after,'Validation changed training weights/Target/Replay/RNG'
    write(folder/'validation-isolation.json',dict(verdict='PASS',before=before,after=after,gradient_updates_during_validation=0))
    stats=dict(step=step,episodes=len(episodes),train_mean_task_reward=None if not step else sum(e['reward'] for e in episodes)/step,
        mean_last_24_episode_reward=None if not episodes else mean(e['reward'] for e in episodes[-24:]),**update_stats)
    write(folder/'training-statistics.json',stats)
    assert agent.updates==max(0,step-63)
    print(f'Checkpoint {agent.algorithm} seed={seed} step={step} updates={agent.updates} target={agent.updates//200}; Validation RNG intact',flush=True)
    return meta,diagnostics

def train_all(training,cases):
    assert json.loads((OUT/'preflight/SOURCE_AND_EVENT_GATE_PASS.json').read_text())['verdict']=='PASS'
    intermediate=intermediate_cases(cases);_,_,estimator=load_data()
    write(OUT/'EVALUATION_PLAN.json',dict(checkpoints=CHECKPOINTS,intermediate_overhead=False,intermediate_cases=[c['exogenous_sha256'] for c in intermediate],
        full_validation_cases=[c['exogenous_sha256'] for c in cases],full_overhead_modes=[False,True],checkpoint_selection='final 9600 for all seeds; no best checkpoint selection',
        baseline_policies=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2'],
        full_policy_order='case/mode-wise shuffled using independent random.Random(20261124)',
        gradient_limit=LIMIT,full_test=False,ridge=False,A_training=False))
    total=0;checkpoints=[];middle=[];summary=[];started=time.perf_counter()
    progress=(OUT/'training-progress.jsonl').open('xb')
    current=None
    try:
        for algorithm,ctor in AGENTS.items():
            for seed in SEEDS:
                schedules=[c for c in training if c['seed']==seed];assert len(schedules)==96
                agent=ctor(seed=seed,gamma=1,input_spec=InputSpec());initial=weights_sha(agent.online)
                folder=OUT/f'models/{algorithm}-s{seed}';folder.mkdir(parents=True)
                episodes=[];steps=0
                stats=dict(gradient_updates=0,td_samples=0,td_clipped=0,gradient_tensors=0,gradient_clipped=0,raw_td_abs_max=0.,
                           q_min=None,q_max=None,q_sum=0.,q_values=0,loss_sum=0.,bootstrap_disagreements=0,bootstrap_samples=0,bootstrap_error_max=0.)
                meta,rows=checkpoint(agent,seed,0,episodes,stats,intermediate,estimator);checkpoints.append(meta);middle.extend(rows)
                with gzip.GzipFile(filename=str(folder/'updates.jsonl.gz'),mode='wb',compresslevel=3,mtime=0) as updates:
                    for ep,case in enumerate(schedules):
                        current=dict(algorithm=algorithm,seed=seed,episode=ep,step=steps,total_training_dispatches=total)
                        env=AuditedIntegralEnv([Task(**r) for r in case['tasks']],**config(case));obs=env.reset();records=[];rewards=0.
                        while obs is not None:
                            if total>=LIMIT or steps>=9600:raise RuntimeError('Authorized training budget exceeded')
                            raw=feature_vector(*obs);p=agent.prepare_state(raw);action=agent.act(raw,case['epsilon']);ad=dict(agent.last_action_diagnostics)
                            assert action in p.available_actions
                            next_obs,reward,done,info=env.step(action);next_raw=raw if done else feature_vector(*next_obs)
                            agent.remember(raw,action,reward,next_raw,done);following=agent.prepare_state(next_raw);stored=agent.memory[-1]
                            assert np.array_equal(stored[0],p.normalized) and np.array_equal(stored[3],following.normalized)
                            assert np.array_equal(stored[5],[float(i in following.available_actions) for i in range(3)])
                            old_online=[w.copy() for w in agent.online];old_target=[w.copy() for w in agent.target]
                            loss=agent.train_step();ud=agent.last_update_diagnostics
                            all_finite(raw,next_raw,ad['q_values'],reward,*agent.online,*agent.target)
                            steps+=1;total+=1
                            if ud is not None:
                                audit=audit_bootstrap(agent,ud,old_online,old_target)
                                record=dict(step=steps,episode=ep,cell=case['cell'],**ud,**audit)
                                updates.write(canonical(record)+b'\n')
                                stats['gradient_updates']+=1;stats['td_samples']+=64;stats['td_clipped']+=ud['td_clip_count']
                                stats['gradient_tensors']+=6;stats['gradient_clipped']+=ud['gradient_clip_count'];stats['loss_sum']+=ud['loss']
                                stats['raw_td_abs_max']=max(stats['raw_td_abs_max'],ud['td_abs_max'])
                                stats['bootstrap_disagreements']+=audit['bootstrap_disagreement_count'];stats['bootstrap_samples']+=64
                                stats['bootstrap_error_max']=max(stats['bootstrap_error_max'],audit['independent_target_error'])
                            q=np.asarray(ad['q_values']);stats['q_min']=float(q.min()) if stats['q_min'] is None else min(stats['q_min'],float(q.min()))
                            stats['q_max']=float(q.max()) if stats['q_max'] is None else max(stats['q_max'],float(q.max()));stats['q_sum']+=float(q.sum());stats['q_values']+=3
                            records.append(dict(step=steps,task_id=obs[0].task_id,action=action,epsilon=case['epsilon'],random_branch=ad['random_branch'],
                                q_values=ad['q_values'],raw_state=list(raw),normalized_state=p.normalized.tolist(),raw_next_state=list(next_raw),normalized_next_state=following.normalized.tolist(),
                                reward=reward,done=done,next_state_kind='terminal_placeholder_no_bootstrap' if done else 'actual_next_decision',loss=loss,
                                rng_after=rng_state(agent),online_sha256=weights_sha(agent.online),update_count=agent.updates,**adaptation(*obs)))
                            rewards+=reward;obs=next_obs
                        rows=env.sim.results;error=conservation(rows);cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in rows)
                        assert len(records)==100 and len(rows)==100 and all(r['completed'] for r in rows)
                        assert abs(rewards+cost)<1e-6 and abs(env.sim.area_ms-sum(r['total_latency_ms'] for r in rows))<1e-6
                        metric=metrics(rows)
                        es=dict(algorithm=algorithm,seed=seed,episode=ep,step=steps,cell=case['cell'],dataset=case['dataset'],load=case['load'],network=case['network'],pattern=case['pattern'],
                            epsilon=case['epsilon'],exogenous_sha256=case['exogenous_sha256'],reward=rewards,**metric,
                            cpu_reversals=sum(r['cpu_component_reversal'] for r in records),network_reversals=sum(r['network_component_reversal'] for r in records),
                            random_count=sum(r['random_branch'] for r in records),median_cost_gap_ms=float(np.median([r['best_second_gap_ms'] for r in records])),
                            time_error_ms=error,reward_error=abs(rewards+cost),resources=resource_guard())
                        gzwrite(folder/f'episodes/e{ep:03d}.json.gz',dict(summary=es,transitions=records,tasks=rows,events=env.sim.events,cost_events=env.sim.cost_events,capacity_maxima=env.capacity_audit.maxima))
                        episodes.append(es);progress.write(canonical(dict(**current,completed_step=steps,completed_total=total))+b'\n');progress.flush()
                        if steps in CHECKPOINTS:
                            meta,rs=checkpoint(agent,seed,steps,episodes,stats,intermediate,estimator);checkpoints.append(meta);middle.extend(rs)
                assert steps==9600 and agent.updates==9537 and agent.updates//200==47
                assert weights_sha(agent.online)!=initial
                write(folder/'training-summary.json',dict(algorithm=algorithm,seed=seed,steps=steps,updates=agent.updates,target_updates=47,episodes=episodes,diagnostics=stats,
                    online_changed=True,final_online_sha256=weights_sha(agent.online),exogenous_stream_sha256=digest([c['exogenous_sha256'] for c in schedules])))
                summary.append(dict(algorithm=algorithm,seed=seed,steps=steps,updates=agent.updates,target_updates=47,**stats))
                print(f'Model complete: {algorithm} seed={seed}; total training {total}/{LIMIT}',flush=True)
        assert total==LIMIT
        write(OUT/'checkpoints.json',checkpoints);gzwrite(OUT/'intermediate-validation.json.gz',middle)
        write(OUT/'training-summary.json',dict(models=summary,total_training_dispatches=total,wall_seconds=time.perf_counter()-started))
        return checkpoints,middle
    except Exception:
        write(OUT/'TRAINING_FAILURE.json',dict(last_progress=current,total_training_dispatches=total,traceback=traceback.format_exc()))
        if 'agent' in locals():
            np.savez_compressed(OUT/'FAILED_AGENT_NOT_A_VALID_MODEL.npz',**{f'online_{i}':w for i,w in enumerate(agent.online)},**{f'target_{i}':w for i,w in enumerate(agent.target)})
        if 'records' in locals():gzwrite(OUT/'failed-episode-partial.json.gz',dict(progress=current,transitions=records))
        raise
    finally:progress.close()

def full_validation(checkpoints,cases):
    _,_,estimator=load_data();policies={};metadata={};signatures={};all_rows=[];started=time.perf_counter()
    for c in checkpoints:
        if c['step']!=9600:continue
        key=f'{c["algorithm"]}-s{c["seed"]}';folder=OUT/f'models/{key}/checkpoints/09600'
        agent=load_agent(c['algorithm'],folder/'policy.npz',c['sha256'],contract_index=folder/'input-contract-index.json');agent.gamma=1
        policies[key]=agent;metadata[key]=c;signatures[key]=fingerprint(agent)
    baselines=['local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2']
    keys=list(policies)+baselines;order_rng=random.Random(20261124);full=OUT/'full-validation';full.mkdir()
    with (full/'summary.jsonl').open('xb') as stream:
        for i,case in enumerate(cases):
            for overhead in (False,True):
                order=list(keys);order_rng.shuffle(order)
                for key in order:
                    result=evaluate_case(case,estimator,overhead,agent=policies.get(key),baseline=key if key in baselines else None,checkpoint=metadata.get(key))
                    row=result['summary'];row['policy_key']=key
                    gzwrite(full/f'raw/{key}/v{i:03d}-cost{int(overhead)}.json.gz',result)
                    all_rows.append(row);stream.write(canonical(row)+b'\n')
            if (i+1)%12==0:
                resource_guard();print(f'Full Validation {i+1}/{len(cases)} cases x 12 policies x 2 cost modes',flush=True)
    for key,agent in policies.items():assert signatures[key]==fingerprint(agent),'Frozen final validation mutated model/RNG'
    gzwrite(full/'summary.json.gz',all_rows)
    write(full/'COMPLETE.json',dict(verdict='PASS',cases=len(cases),policies=12,cost_modes=2,task_dispatches=len(cases)*12*2*100,
        gradient_updates=0,wall_seconds=time.perf_counter()-started,all_candidates_kept=True,frozen_models_unchanged=True,formal_test=False))
    return all_rows

if __name__=='__main__':
    if (OUT/'TRAINING_RESERVED.json').exists():raise RuntimeError('Single-use training run; do not duplicate authorized dispatches')
    write(OUT/'TRAINING_RESERVED.json',dict(maximum_total=LIMIT,models=6,per_model=9600,checkpoints=CHECKPOINTS))
    try:
        t=json.loads((ROOT/'results/design/training-manifest.json').read_text())['training']
        cases=json.loads((ROOT/'results/design/validation-manifest.json').read_text())['cases']
        checkpoints,middle=train_all(t,cases)
        full_validation(checkpoints,cases)
        write(OUT/'COMPLETE.json',dict(verdict='PASS',training_dispatches=57600,models=6,checkpoints=30,
            intermediate_validation_dispatches=72000,full_validation_dispatches=576000,formal_test=False,A_training=False,Ridge=False,extended14400=False))
    except Exception:
        if not (OUT/'RUN_FAILURE.json').exists():write(OUT/'RUN_FAILURE.json',dict(traceback=traceback.format_exc()))
        raise
