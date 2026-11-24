"""Hard-limited B-v1 smoke: four histories x 600 decisions; no full training CLI."""
from collections import Counter
from dataclasses import asdict
import json,resource,time
from pathlib import Path
from statistics import mean
import numpy as np
from common import ROOT,arrays_equal,canonical,digest,file_sha,rng_state,weight_sha,write,table
from design import config,smoke_subset,validation_subset
from diagnostics import AGENTS
from evidence import AuditedIntegralEnv,adaptation,conservation
from validation import evaluate
from app.offloading.models import Task
from app.offloading.integration_contract import feature_vector
from app.offloading.experiment import metrics
from app.offloading.agents49.adapter import Agent49Policy,load_agent
from app.offloading.agents49.input_contract import InputSpec,export_agent_contract,write_contract_index

LIMIT=2400
def run(manifest,out):
    marker=out/'SMOKE_STARTED.json'
    write(marker,dict(limit=LIMIT,per_history_limit=600,explicit_full_training_authorization=False))
    selected=smoke_subset(manifest);v=validation_subset(manifest)
    write(out/'smoke-subset.json',dict(training_cells=[r['cell'] for r in selected],training_exogenous_sha256=[r['exogenous_sha256'] for r in selected],
        validation_cells=[r['cell'] for r in v],validation_cases=len(v),training_decisions_per_history=600,independent_training_pool_images=80,
        unique_images_in_smoke=len({t['source_path'] for c in selected for t in c['tasks']})))
    total=0;models=[];summaries=[];paired={};started=time.perf_counter();validate_calls=0
    for algorithm,ctor in AGENTS.items():
        reference=None
        for insertion in (False,True):
            branch='with-validation' if insertion else 'without-validation';folder=out/algorithm/branch
            folder.mkdir(parents=True)
            agent=ctor(seed=42,gamma=1,input_spec=InputSpec())
            initial=[w.copy() for w in agent.online];history=[];episodes=[];transitions=[];updates=[]
            for ep,case in enumerate(selected):
                env=AuditedIntegralEnv([Task(**r) for r in case['tasks']],**config(case));obs=env.reset();episode_reward=0.;step_records=[]
                while obs is not None:
                    if total>=LIMIT or len(history)>=600:raise RuntimeError('Hard smoke training dispatch limit reached')
                    f=feature_vector(*obs);input_before=agent.prepare_state(f)
                    adapter=Agent49Policy(agent);adapter_action=adapter.choose(f);adapter_trace=adapter.decisions[-1]
                    assert np.array_equal(input_before.normalized,adapter_trace['normalized_features'])
                    before_rng=rng_state(agent);action=agent.act(f,case['epsilon']);ad=dict(agent.last_action_diagnostics)
                    assert ad['greedy_action']==adapter_action and np.array_equal(ad['q_values'],adapter_trace['q_values'])
                    next_obs,reward,done,info=env.step(action)
                    nf=f if done else feature_vector(*next_obs)
                    agent.remember(f,action,reward,nf,done)
                    replay=agent.memory[-1];following=agent.prepare_state(nf)
                    assert np.array_equal(replay[0],input_before.normalized) and np.array_equal(replay[3],following.normalized)
                    assert np.array_equal(replay[5],[float(i in following.available_actions) for i in range(3)])
                    loss=agent.train_step();ud=agent.last_update_diagnostics
                    assert all(np.isfinite(w).all() for w in agent.online+agent.target)
                    assert np.isfinite(np.r_[f,nf,ad['q_values'],reward]).all()
                    diag=adaptation(*obs)
                    record=dict(step=len(history),episode=ep,cell=case['cell'],task_id=obs[0].task_id,action=action,
                        random_branch=ad['random_branch'],epsilon=case['epsilon'],q_values=ad['q_values'],
                        raw_state=list(f),raw_next_state=list(nf),normalized_state=input_before.normalized.tolist(),
                        normalized_next_state=following.normalized.tolist(),episode_done=done,
                        next_state_kind='terminal_placeholder_no_bootstrap' if done else 'actual_next_decision',
                        reward=reward,loss=loss,rng_before=before_rng,rng_after=rng_state(agent),
                        online_sha256=weight_sha(agent),target_sha256=digest([w.tolist() for w in agent.target]),
                        replay_size=len(agent.memory),update_count=agent.updates,**diag)
                    history.append({k:record[k] for k in ('action','reward','episode_done','rng_after','online_sha256','target_sha256','replay_size','update_count')})
                    if reference is not None:assert history[-1]==reference[len(history)-1],f'Training path differs at {algorithm} {len(history)}'
                    step_records.append(record);transitions.append(record)
                    if ud is not None:updates.append(dict(step=len(history),episode=ep,cell=case['cell'],**ud))
                    total+=1;episode_reward+=reward;obs=next_obs
                error=conservation(env.sim.results)
                independent_cost=sum(r['total_latency_ms']/1000+int(not r['deadline_met']) for r in env.sim.results)
                assert abs(episode_reward+independent_cost)<1e-6
                assert abs(env.sim.area_ms-sum(r['total_latency_ms'] for r in env.sim.results))<1e-6
                counts=Counter(r['action'] for r in step_records)
                episode=dict(episode=ep,cell=case['cell'],exogenous_sha256=case['exogenous_sha256'],
                    episode_reward=episode_reward,**metrics(env.sim.results),
                    cpu_component_reversals=sum(r['cpu_component_reversal'] for r in step_records),
                    network_component_reversals=sum(r['network_component_reversal'] for r in step_records),
                    minimum_cost_gap_ms=min(r['best_second_gap_ms'] for r in step_records),
                    median_cost_gap_ms=float(np.median([r['best_second_gap_ms'] for r in step_records])),
                    random_branch_count=sum(r['random_branch'] for r in step_records),
                    capacity_maxima=env.capacity_audit.maxima,events_observed=env.capacity_audit.steps,time_error_ms=error)
                episodes.append(episode)
                write(folder/f'episode-{ep}.json',dict(summary=episode,transitions=step_records,tasks=env.sim.results,events=env.sim.events,cost_events=env.sim.cost_events))
                if insertion and len(history)==300:
                    before=(rng_state(agent),weight_sha(agent),agent.updates)
                    first=evaluate(agent,v[:1],False);second=evaluate(agent,v[:1],False);validate_calls+=200
                    assert first[0]['signature']==second[0]['signature']
                    assert before==(rng_state(agent),weight_sha(agent),agent.updates)
                    write(folder/'inserted-validation.json',dict(first=first,second=second,deterministic_signature=True,training_unchanged=True))
            assert len(history)==600 and agent.updates==537 and len(agent.memory)==600
            assert not arrays_equal(initial,agent.online)
            assert sum(r['target_synchronized'] for r in updates)==2
            assert all(r['loss'] is not None for r in updates)
            if reference is None:reference=history
            else:assert history==reference
            weight=folder/'smoke-only.npz';agent.save(weight)
            write(folder/'checkpoint-metadata.json',dict(algorithm=algorithm,sha256=file_sha(weight),steps=600,updates=537,target_updates=2,
                seed=42,role='SMOKE_ONLY_NOT_FORMAL_MODEL',objective='integral',gamma=1,feature_mask=[],validation_inserted=insertion))
            sources=[folder/'checkpoint-metadata.json']+[ROOT/'tools'/f for f in ('smoke.py','design.py','diagnostics.py','evidence.py')]+[ROOT/'runtime/backend/app/offloading/agents49'/f for f in ('dqn.py','ddqn.py','input_contract.py','normalizer.py','integral_env.py')]
            ref=export_agent_contract(agent,weight,folder/'input-contracts',sources)
            write_contract_index(folder/'input-contract-index.json',[ref])
            loaded=load_agent(algorithm,weight,file_sha(weight),contract_index=folder/'input-contract-index.json')
            loaded.gamma=1 # Frozen evaluation only; constructor default is not the training hyperparameter.
            # Independent raw-weight formula against production Adapter.
            raw=np.array(transitions[0]['raw_state']);normalizer=loaded.input_spec.to_dict()['normalizer']
            x=np.log1p(raw/normalizer['scales']);x[[14,28,42]]=raw[[14,28,42]]
            w1,b1,w2,b2,w3,b3=loaded.online;q=np.maximum(np.maximum(x@w1+b1,0)@w2+b2,0)@w3+b3
            _,observed_q,_=loaded.predict_greedy(raw)
            assert np.allclose(q,observed_q,rtol=1e-12,atol=1e-12)
            write(folder/'updates.json',updates)
            table(folder/'episode-summary.csv',[dict(episode=e['episode'],cell=e['cell'],reward=e['episode_reward'],mean_ms=e['avg_latency_ms'],p95_ms=e['p95_latency_ms'],deadline=e['deadline_met_rate'],
                local=e['placement_ratio']['local'],edge=e['placement_ratio']['edge'],cloud=e['placement_ratio']['cloud'],cpu_reversals=e['cpu_component_reversals'],network_reversals=e['network_component_reversals'],random=e['random_branch_count']) for e in episodes])
            models.append((algorithm,branch,loaded,folder));paired[algorithm]=True
            summaries.append(dict(algorithm=algorithm,branch=branch,steps=600,updates=537,target_updates=2,
                reward=sum(e['episode_reward'] for e in episodes),mean_ms=mean(e['avg_latency_ms'] for e in episodes),
                p95_ms=float(np.sort([r['total_latency_ms'] for ep in range(6) for r in json.loads((folder/f'episode-{ep}.json').read_text())['tasks']])[569]),
                deadline_met_rate=mean(e['deadline_met_rate'] for e in episodes),
                local_ratio=sum(e['placement']['local'] for e in episodes)/600,edge_ratio=sum(e['placement']['edge'] for e in episodes)/600,cloud_ratio=sum(e['placement']['cloud'] for e in episodes)/600,
                cpu_reversals=sum(e['cpu_component_reversals'] for e in episodes),network_reversals=sum(e['network_component_reversals'] for e in episodes),
                random_branch_count=sum(e['random_branch_count'] for e in episodes),max_abs_td=max(r['td_abs_max'] for r in updates),
                td_clipped_samples=sum(r['td_clip_count'] for r in updates),td_total_samples=len(updates)*64,
                gradient_clipped_tensors=sum(r['gradient_clip_count'] for r in updates),q_min=min(r['q_min'] for r in updates),q_max=max(r['q_max'] for r in updates),
                final_weight_sha256=file_sha(weight),new_online_changed=True,numeric_finite=True,independent_q_error=float(np.max(np.abs(q-observed_q)))))
            print(algorithm,branch,'600 decisions; 537 updates; 2 target copies',flush=True)
    assert total==LIMIT
    # Limited frozen Validation evaluation, common subset, no ranking / selection.
    validation_rows=[]
    for algorithm,branch,agent,folder in models:
        for overhead in (False,True):
            evaluated=evaluate(agent,v,overhead);validate_calls+=len(v)*100
            for i,result in enumerate(evaluated):
                write(folder/f'validation/v{i:02d}-cost{int(overhead)}.json',result)
                validation_rows.append(dict(policy=algorithm,branch=branch,cell=result['cell'],overhead=overhead,
                    reward=result['episode_reward'],mean_ms=result['summary']['avg_latency_ms'],p95_ms=result['summary']['p95_latency_ms'],deadline=result['summary']['deadline_met_rate'],exogenous_sha256=result['exogenous_sha256']))
    for baseline in ('local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2'):
        for overhead in (False,True):
            evaluated=evaluate(None,v,overhead,baseline);validate_calls+=len(v)*100
            for i,result in enumerate(evaluated):
                write(out/f'baselines/{baseline}/v{i:02d}-cost{int(overhead)}.json',result)
                validation_rows.append(dict(policy=baseline,branch='fixed_validation',cell=result['cell'],overhead=overhead,
                    reward=result['episode_reward'],mean_ms=result['summary']['avg_latency_ms'],p95_ms=result['summary']['p95_latency_ms'],deadline=result['summary']['deadline_met_rate'],exogenous_sha256=result['exogenous_sha256']))
    table(out/'validation-subset-summary.csv',validation_rows);table(out/'smoke-model-summary.csv',summaries)
    write(out/'smoke-model-summary.json',summaries)
    write(out/'COMPLETE.json',dict(verdict='PASS',training_dispatches=total,gradient_updates_per_history=537,target_updates_per_history=2,
        paired_rng_and_weights_equal=paired,validation_dispatches=validate_calls,full_training_run=False,formal_test_run=False,
        ridge_run=False,wall_seconds=time.perf_counter()-started,max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        note='Only seed42, 6/48 training cells; no convergence or ranking claim'))
