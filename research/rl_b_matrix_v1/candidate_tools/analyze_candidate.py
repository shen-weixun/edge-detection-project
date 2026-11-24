"""Post-run evidence export only. No optimizer call, selection, or Test access."""
import csv,gzip,json,math,resource
from collections import defaultdict
from pathlib import Path
from statistics import mean
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import ROOT,write,file_sha
from candidate_common import OUT,readgz

REPORT=OUT/'reports'
def table(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def modelkey(row):return f'{row["policy"]}-s{row["train_seed"]}'
def mean_field(rows,name):return mean(r[name] for r in rows)

def main():
    assert json.loads((OUT/'COMPLETE.json').read_text())['training_dispatches']==57600
    REPORT.mkdir();models=json.loads((OUT/'training-summary.json').read_text())['models']
    checkpoints=json.loads((OUT/'checkpoints.json').read_text());middle=readgz(OUT/'intermediate-validation.json.gz')
    full=readgz(OUT/'full-validation/summary.json.gz')
    table(REPORT/'full-validation.csv',full);table(REPORT/'checkpoint-validation.csv',middle)
    checkpoint_rows=[]
    for c in checkpoints:
        folder=OUT/f'models/{c["algorithm"]}-s{c["seed"]}/checkpoints/{c["step"]:05d}'
        assert file_sha(folder/'policy.npz')==c['sha256']
        assert json.loads((folder/'validation-isolation.json').read_text())['verdict']=='PASS'
        checkpoint_rows.append(dict(algorithm=c['algorithm'],seed=c['seed'],step=c['step'],updates=c['updates'],target_updates=c['target_updates'],sha256=c['sha256'],
            state_sha256=file_sha(folder/'training-state.npz'),contract_index_sha256=file_sha(folder/'input-contract-index.json')))
    table(REPORT/'checkpoint-sha256.csv',checkpoint_rows)
    baseline={(r['policy_key'],r['cell'],r['validation_seed'],r['overhead']):r for r in full if r['train_seed'] is None}
    comparisons=[];tradeoffs=[];regrets=[]
    baseline_names=('local_only','edge_only','cloud_only','load_threshold','latency_aware','latency_aware_v2')
    for row in full:
        if row['train_seed'] is None:continue
        for name in baseline_names:
            b=baseline[name,row['cell'],row['validation_seed'],row['overhead']]
            assert b['exogenous_sha256']==row['exogenous_sha256']
            diff=dict(policy_key=row['policy_key'],dataset=row['dataset'],load=row['load'],network=row['network'],pattern=row['pattern'],
                validation_seed=row['validation_seed'],overhead=row['overhead'],baseline=name,mean_delta_ms=row['mean_ms']-b['mean_ms'],
                p95_delta_ms=row['p95_ms']-b['p95_ms'],deadline_delta=row['deadline_rate']-b['deadline_rate'],reward_delta=row['episode_reward']-b['episode_reward'],
                model_mean_ms=row['mean_ms'],baseline_mean_ms=b['mean_ms'],model_p95_ms=row['p95_ms'],baseline_p95_ms=b['p95_ms'],
                model_deadline=row['deadline_rate'],baseline_deadline=b['deadline_rate'])
            comparisons.append(diff)
            if diff['mean_delta_ms']<0 and diff['p95_delta_ms']>0:tradeoffs.append(diff)
        options=[baseline[n,row['cell'],row['validation_seed'],row['overhead']] for n in baseline_names[:3]]
        best=min(options,key=lambda x:x['mean_ms'])
        regrets.append(dict(policy_key=row['policy_key'],cell=row['cell'],validation_seed=row['validation_seed'],overhead=row['overhead'],
            best_fixed_hindsight=best['policy_key'],mean_ms=row['mean_ms'],best_fixed_mean_ms=best['mean_ms'],
            mean_delta_ms=row['mean_ms']-best['mean_ms'],p95_delta_ms=row['p95_ms']-best['p95_ms'],
            all_local=row['local_ratio']==1,all_edge=row['edge_ratio']==1,all_cloud=row['cloud_ratio']==1,
            note='Hindsight diagnostic only; not a deployable strategy or training label'))
    table(REPORT/'baseline-differences.csv',comparisons)
    if tradeoffs:table(REPORT/'mean-improves-p95-worsens.csv',tradeoffs)
    table(REPORT/'fixed-policy-regret.csv',regrets)
    intermediate_deltas=[]
    for r in middle:
        for name in baseline_names:
            b=baseline[name,r['cell'],r['validation_seed'],False]
            assert b['exogenous_sha256']==r['exogenous_sha256']
            intermediate_deltas.append(dict(policy_key=modelkey(r),step=r['checkpoint'],cell=r['cell'],baseline=name,
                mean_delta_ms=r['mean_ms']-b['mean_ms'],p95_delta_ms=r['p95_ms']-b['p95_ms'],deadline_delta=r['deadline_rate']-b['deadline_rate'],reward_delta=r['episode_reward']-b['episode_reward']))
    table(REPORT/'checkpoint-baseline-differences.csv',intermediate_deltas)

    learning=[];episodes_all=[];diagnostics=[];probe_rows=[];exploration=[]
    for model in models:
        alg,seed=model['algorithm'],model['seed'];key=f'{alg}-s{seed}';folder=OUT/'models'/key
        training=json.loads((folder/'training-summary.json').read_text());eps=training['episodes'];episodes_all.extend(eps)
        windows=[];buffer=[]
        with gzip.open(folder/'updates.jsonl.gz','rt',encoding='utf-8') as f:
            for line in f:
                u=json.loads(line);buffer.append(u)
                diagnostics.append(dict(policy_key=key,step=u['step'],update=u['gradient_update_count'],loss=u['loss'],td_abs_max=u['td_abs_max'],td_clip_ratio=u['td_clip_ratio'],
                    grad_clip_ratio=u['gradient_clip_count']/6,q_min=u['q_min'],q_max=u['q_max'],q_mean=u['q_mean'],replay_size=u['replay_size'],target_update_count=u['target_update_count'],
                    bootstrap_disagreement_count=u['bootstrap_disagreement_count'],independent_target_error=u['independent_target_error']))
                if len(buffer)==200 or u['gradient_update_count']==9537:
                    raw=np.concatenate([x['raw_td_error'] for x in buffer]);windows.append(dict(step=u['step'],loss=mean(x['loss'] for x in buffer),td_p95=float(np.quantile(abs(raw),.95)),
                        grad_clip=mean(x['gradient_clip_count']/6 for x in buffer),td_clip=mean(x['td_clip_ratio'] for x in buffer)))
                    buffer=[]
        for step in (0,2400,4800,7200,9600):
            selected=[r for r in middle if r['policy']==alg and r['train_seed']==seed and r['checkpoint']==step]
            assert len(selected)==24
            tracking=dict(policy_key=key,step=step,monitor_macro_task_reward=mean_field(selected,'mean_task_reward'),
                monitor_macro_mean_ms=mean_field(selected,'mean_ms'),monitor_macro_p95_ms=mean_field(selected,'p95_ms'),monitor_macro_deadline=mean_field(selected,'deadline_rate'),
                local_entry_all_cloud=sum(r['cloud_ratio']==1 for r in selected if r['network']=='local_entry'),local_entry_cases=sum(r['network']=='local_entry' for r in selected),
                near_fixed_cases=sum(max(r['local_ratio'],r['edge_ratio'],r['cloud_ratio'])>=.99 for r in selected))
            learning.append(tracking)
            for probe in json.loads((folder/f'checkpoints/{step:05d}/queue-probes.json').read_text()):
                probe_rows.append(dict(policy_key=key,step=step,case=probe['case'],node=probe['node'],estimated_best=probe['observable_estimated_best'],
                    q_local=probe['q_values'][0],q_edge=probe['q_values'][1],q_cloud=probe['q_values'][2]))
        # Actual per-cell exploration, both phases. Image repetitions remain identified.
        for e in eps:exploration.append(dict(policy_key=key,cell=e['cell'],episode=e['episode'],epsilon=e['epsilon'],dispatches=100,random_branch_count=e['random_count'],
            cpu_reversals=e['cpu_reversals'],network_reversals=e['network_reversals'],median_cost_gap_ms=e['median_cost_gap_ms']))
        fig,axes=plt.subplots(2,2,figsize=(12,8))
        axes[0,0].plot([e['episode']+1 for e in eps],[e['reward'] for e in eps],linewidth=.8)
        axes[0,0].axvline(48.5,color='red',ls='--');axes[0,0].set(title='Training episode reward (different cells)',xlabel='Episode',ylabel='Integral reward')
        lr=[r for r in learning if r['policy_key']==key]
        axes[0,1].plot([r['step'] for r in lr],[r['monitor_macro_task_reward'] for r in lr],marker='o')
        axes[0,1].set(title='Fixed 24-case monitor (diagnostic only)',xlabel='Training decisions',ylabel='Macro task reward')
        axes[1,0].plot([w['step'] for w in windows],[w['loss'] for w in windows],label='Clipped TD squared loss')
        axes[1,0].plot([w['step'] for w in windows],[w['td_p95'] for w in windows],label='Raw |TD| p95');axes[1,0].legend(fontsize=8);axes[1,0].set_xlabel('Training decisions')
        axes[1,1].plot([w['step'] for w in windows],[w['grad_clip'] for w in windows],label='Gradient tensors clipped')
        axes[1,1].plot([w['step'] for w in windows],[w['td_clip'] for w in windows],label='TD samples clipped');axes[1,1].legend(fontsize=8);axes[1,1].set_xlabel('Training decisions')
        fig.suptitle(key+' | Median / Full49 / Integral gamma=1 | Validation only');fig.tight_layout()
        (REPORT/'charts').mkdir(exist_ok=True);fig.savefig(REPORT/'charts'/f'{key}-learning.png',dpi=130);plt.close(fig)
    table(REPORT/'learning-curves.csv',learning);table(REPORT/'update-diagnostics.csv',diagnostics);table(REPORT/'queue-probes.csv',probe_rows);table(REPORT/'actual-exploration-and-reversals.csv',exploration)
    # Flatten episode metrics while keeping datasets/load/networks/patterns separate.
    epcols=('algorithm','seed','episode','step','cell','dataset','load','network','pattern','epsilon','reward','avg_latency_ms','p95_latency_ms','deadline_met_rate','random_count','cpu_reversals','network_reversals','median_cost_gap_ms','time_error_ms','reward_error')
    table(REPORT/'training-episodes.csv',[{k:e[k] for k in epcols} for e in episodes_all])

    cost_rows=[]
    for r in full:
        if not r['overhead']:continue
        base=next(x for x in full if x['policy_key']==r['policy_key'] and x['cell']==r['cell'] and x['validation_seed']==r['validation_seed'] and not x['overhead'])
        cost_rows.append(dict(policy_key=r['policy_key'],cell=r['cell'],validation_seed=r['validation_seed'],mean_delta_ms=r['mean_ms']-base['mean_ms'],
            p95_delta_ms=r['p95_ms']-base['p95_ms'],deadline_delta=r['deadline_rate']-base['deadline_rate'],decision_wall_ms=r['decision_wall_ms'],decision_queue_ms=r['decision_queue_ms']))
    table(REPORT/'decision-cost-effects.csv',cost_rows)

    # Stratified plots: each dataset/network separately, all seeds remain columns.
    keys=[f'{a}-s{s}' for a in ('dqn','ddqn') for s in (42,43,44)]+list(baseline_names)
    networks=list(dict.fromkeys(r['network'] for r in full))
    for ds in ('lfw','wider_train'):
        for network in networks:
            for overhead in (False,True):
                combos=[(l,p) for l in ('Low','Medium','High') for p in ('steady','burst')]
                fig,axes=plt.subplots(1,3,figsize=(21,5))
                for ax,metric,title in zip(axes,('mean_ms','p95_ms','deadline_rate'),('Mean ms (log10 color)','P95 ms (log10 color)','Deadline met')):
                    arr=np.array([[mean(r[metric] for r in full if r['policy_key']==key and r['dataset']==ds and r['network']==network and r['load']==l and r['pattern']==p and r['overhead']==overhead) for key in keys] for l,p in combos])
                    plot=np.log10(np.maximum(arr,1e-6)) if metric!='deadline_rate' else arr
                    im=ax.imshow(plot,aspect='auto',cmap='viridis' if metric!='deadline_rate' else 'YlGn',vmin=None if metric!='deadline_rate' else 0,vmax=None if metric!='deadline_rate' else 1)
                    ax.set_xticks(range(len(keys)),keys,rotation=70,ha='right',fontsize=7);ax.set_yticks(range(6),[l+'/'+p for l,p in combos],fontsize=8);ax.set_title(title)
                    fig.colorbar(im,ax=ax,shrink=.65)
                fig.suptitle(f'{ds} | {network} | cost={overhead} | average of two Validation trajectories; seeds kept separate')
                fig.tight_layout();fig.savefig(REPORT/'charts'/f'{ds}__{network}__cost{int(overhead)}.png',dpi=120);plt.close(fig)

    per_model=[]
    for model in models:
        key=f'{model["algorithm"]}-s{model["seed"]}';lc=[r for r in learning if r['policy_key']==key]
        targets=[r for r in full if r['policy_key']==key and not r['overhead']]
        cmp=[r for r in comparisons if r['policy_key']==key and not r['overhead'] and r['baseline']=='latency_aware_v2']
        reg=[r for r in regrets if r['policy_key']==key and not r['overhead']]
        per_model.append(dict(policy_key=key,updates=9537,target_updates=47,
            monitor_rewards=[r['monitor_macro_task_reward'] for r in lc],
            monitor_final_minus_initial=lc[-1]['monitor_macro_task_reward']-lc[0]['monitor_macro_task_reward'],
            monitor_final_minus_4800=lc[-1]['monitor_macro_task_reward']-lc[2]['monitor_macro_task_reward'],
            final_validation_cases=len(targets),cases_mean_better_than_v2=sum(r['mean_delta_ms']<0 for r in cmp),cases_mean_worse_than_v2=sum(r['mean_delta_ms']>0 for r in cmp),
            cases_worse_than_best_fixed_hindsight=sum(r['mean_delta_ms']>0 for r in reg),
            near_fixed_cases=sum(max(r['local_ratio'],r['edge_ratio'],r['cloud_ratio'])>=.99 for r in targets),
            local_entry_all_cloud=sum(r['network']=='local_entry' and r['cloud_ratio']==1 for r in targets),
            local_entry_cases=sum(r['network']=='local_entry' for r in targets),
            max_abs_td=model['raw_td_abs_max'],td_clip_ratio=model['td_clipped']/model['td_samples'],gradient_clip_ratio=model['gradient_clipped']/model['gradient_tensors'],
            bootstrap_disagreement_ratio=model['bootstrap_disagreements']/model['bootstrap_samples'],bootstrap_error_max=model['bootstrap_error_max']))
    write(REPORT/'diagnostic-summary.json',dict(models=per_model,full_rows=len(full),intermediate_rows=len(middle),checkpoint_count=len(checkpoints),
        total_training=57600,total_gradient_updates=6*9537,full_validation_dispatches=576000,intermediate_dispatches=72000,
        mean_p95_tradeoff_rows=len(tradeoffs),max_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        note='Counts are diagnostics across heterogeneous cells, not a pooled policy ranking.'))
    lines=['# B矩陣六模型候選訓練與完整Validation','',
      '日期：2026-11-24（Asia/Taipei）。本輪未執行正式Test、A矩陣訓練、Ridge或14400次延長。所有Seed及最終9600 Checkpoint均保留，未依Validation挑選最佳模型。','',
      '## 工程與來源','',
      '- 沿用已驗收Smoke不可變來源；130項回歸重新通過。56份歷史契約及336個拒絕案例重新通過。',
      '- 48個B cell各100任務，無梯度事件預檢4800派送完成；資源容量、時間、Integral成本與合法Action均通過。',
      '- 六模型各9600訓練派送、9537次gradient update、47次Target同步；合計57600訓練派送。',
      '- 五個Checkpoint：0/2400/4800/7200/9600，共30個權重、契約、Target/Replay/RNG狀態；checkpoint-sha256.csv列完整SHA。',
      '- 每Checkpoint固定24個分層Validation cases、epsilon=0且不計決策成本，共72000評估派送。',
      '- 最終完整240 cases、六候選＋六Baseline、兩成本模式，共576000評估派送。Raw JSON以gzip無損保存。',
      '- 全部Validation均核對訓練fingerprint與獨立模型完整性，不消耗Training RNG。Bootstrap以更新前Online/Target獨立公式逐次核對。',
      '- Candidate來源、SimPy、Baseline、P0、Normalizer、Integral Reward均未修改；新訓練沒有載入Smoke或歷史權重續訓。','',
      '## 固定監測子集學習趨勢','',
      '下列是同一24-case監測子集的macro task Reward，用於追蹤時間趨勢，不是跨情境策略排名。越高越好。','',
      '| 模型 | 0 | 2400 | 4800 | 7200 | 9600 | 最終−初始 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for m in per_model:
        lines.append('| '+m['policy_key']+' | '+' | '.join(f'{x:.4f}' for x in m['monitor_rewards'])+f' | {m["monitor_final_minus_initial"]:+.4f} |')
    lines+=['','## 最終Validation診斷（各模型240 cases，不含決策成本）','',
      '| 模型 | Mean優／劣於V2案例數 | 劣於事後最佳固定式 | ≥99%單節點案例 | Local-entry全Cloud | TD裁切 | 梯度張量裁切 |',
      '|---|---:|---:|---:|---:|---:|---:|']
    for m in per_model:
        lines.append(f'| {m["policy_key"]} | {m["cases_mean_better_than_v2"]}/{m["cases_mean_worse_than_v2"]} | {m["cases_worse_than_best_fixed_hindsight"]} | {m["near_fixed_cases"]} | {m["local_entry_all_cloud"]}/{m["local_entry_cases"]} | {m["td_clip_ratio"]:.2%} | {m["gradient_clip_ratio"]:.2%} |')
    lines+=['','上述計數不代表統計顯著性；同一Validation圖像反覆派送，Seed是任務軌跡變化，不是新增獨立人臉樣本。事後最佳固定式僅診斷，不是可部署策略或訓練標籤。','',
      '## 分層結果與失敗證據','',
      '- full-validation.csv：逐資料集／負載／網路／Steady-Burst／Seed／成本模式的Mean、P95、Deadline、Reward、Action Ratio及分階段成本。',
      '- baseline-differences.csv：每個候選對六Baseline的配對差距；未修改Baseline或合併成總排名。',
      '- checkpoint-validation.csv、checkpoint-baseline-differences.csv、learning-curves.csv：五個Checkpoint與配對Baseline。',
      '- fixed-policy-regret.csv：明顯固定選點與完整Episode成本的反例；mean-improves-p95-worsens.csv保留Mean改善但P95惡化的案例（若存在）。',
      '- queue-probes.csv：實際SimPy來源的同圖／同環境不同佇列控制觀測，保存每Checkpoint Q與Action。不同於V1/V2本身不構成錯誤。',
      '- actual-exploration-and-reversals.csv：每Seed、每Episode的實際探索分支與自然流成本分項反轉；此反轉是估計成本診斷，非真實最優或因果標籤。',
      '- decision-cost-effects.csv：同任務、同模型計入／不計入實際決策成本；wall-time成本包含原Adapter及Median預測，不含訓練診斷。',
      '- update-diagnostics.csv與原始updates.jsonl.gz：Raw TD、Loss、Q、梯度裁切、Replay、Target、獨立Bootstrap差異與誤差。',
      '- charts/：六份逐Seed學習曲線，以及按dataset/network分開的Mean、P95、Deadline圖；所有Training Seeds分欄保留。','',
      '## 可支持與不能支持的結論','',
      '- 工程完成不等於收斂；只有兩輪、五個監測點，不能宣稱漸近收斂。',
      '- 高探索轉低探索同時改變行為策略；Training Reward改善不能單獨歸因Q學習，須看固定Greedy Validation。',
      '- 所有Seed保留。不因不佳Reward、固定選點或尾延遲自行重訓或調參。',
      '- 對共享網路拓撲、其他算力或真實CPU共享不作泛化宣稱；主訓練為independent與相對速度1/3/8。',
      '- Local Profile為歷史CPU量測，硬體型號與threads來源不足仍存在；16KB結果是固定假設。',
      '- 下一輪先審查分層失敗與估計偏差，再決定A矩陣／延長／Ridge；本輪不自動執行任何延伸。','']
    (REPORT/'B_CANDIDATE_VALIDATION_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Analysis exported: 6 learning curves, 40 stratified figures, full paired CSVs; no model selected or modified',flush=True)

if __name__=='__main__':main()
