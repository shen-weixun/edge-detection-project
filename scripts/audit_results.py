"""Verify persisted nine-run evidence and produce reviewable before/after tables.
Run after run_sensitivity.py. Does not rerun or modify experiments.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

COSTS = ('decision_ms','decision_queue_ms','network_ms','queue_ms','compute_ms')
IDENTITY = ('task_id','image_size_mb','face_count','workload_ms','source_path','dataset','sample_id')


def analyze(before, after, audit_path, output):
    output.mkdir(parents=True,exist_ok=True)
    audits={r['audit_id']:r for r in map(json.loads,audit_path.read_text(encoding='utf-8-sig').splitlines())}
    comparisons=[]; checks=[]; records=[]; max_error=0; truncated=0; batch=None
    for interval in (70,300,1000):
        for deadline in (500,1000,2000):
            filename=f'interval-{interval}-deadline-{deadline}.json'
            old=json.loads((before/filename).read_text(encoding='utf-8-sig'))
            new=json.loads((after/filename).read_text(encoding='utf-8-sig'))
            def check(name,condition):
                assert condition,(filename,name)
                checks.append(dict(scenario=filename,check=name,status='PASS'))
            check('same actual image identities/order/workload',
                  [{k:t[k] for k in IDENTITY} for t in old['workload']]==[{k:t[k] for k in IDENTITY} for t in new['workload']])
            check('same node parameters',old['config']['nodes']==new['config']['nodes'])
            check('formal realistic/independent/complete_all',new['information_mode']=='realistic' and
                  new['decision_overhead_in_latency'] and new['config']['network_mode']=='independent' and
                  new['config']['deadline_policy']=='complete_all')
            digest=hashlib.sha256(json.dumps([{k:t[k] for k in IDENTITY} for t in new['workload']],sort_keys=True).encode()).hexdigest()
            if batch is None:batch=digest
            check('same image batch across nine runs',batch==digest)
            test_ids={(t['dataset'],t['source_path']) for t in new['workload']}
            check('calibration identities disjoint',not test_ids.intersection(map(tuple,new['estimator']['training_identities'])))
            for strategy,result in new['strategies'].items():
                check(strategy+' identical manifest',[t['task'] for t in result['tasks']]==new['workload'])
                for row in result['tasks']:
                    error=abs(row['total_latency_ms']-sum(row[k] for k in COSTS));max_error=max(max_error,error)
                    assert error<1e-7
                    assert abs(row['total_latency_ms']-(row['completed_at_ms']-row['arrival_ms']))<1e-7
                    assert row['completed'] and not row['dropped']
                    assert 'workload_ms' not in row['decision_input'] and 'face_count' not in row['decision_input']
                    assert row['decision_input']['estimated_workload_ms']==new['estimator']['estimate_ms']
                    if strategy=='laya':
                        a=audits[row['decision_audit_id']]
                        assert a['final_choice']==a['raw_output']['answers']['offload_target']['choice']==row['selected_node']
                        assert not a['fallback_used'] and not a.get('error')
                        assert a['state']['task']==row['decision_input']
                        assert 'workload_ms' not in a['state']['task'] and 'face_count' not in a['state']['task']
                        truncated+=bool(a['raw_output'].get('usage',{}).get('truncated'))
                        records.append(a)
                values={}
                for prefix,record in [('before',old['strategies'][strategy]),('after',result)]:
                    s=record['summary']
                    for key in ('avg_latency_ms','p95_latency_ms','deadline_met_rate','avg_decision_ms'):
                        values[prefix+'_'+key]=s[key]
                    for key in COSTS:values[prefix+'_'+key]=s['components_ms'][key]
                    for node in ('local','edge','cloud'):values[prefix+'_'+node+'_ratio']=s['placement_ratio'][node]
                comparisons.append(dict(interval_ms=interval,deadline_ms=deadline,strategy=strategy,**values,
                                        delta_avg_latency_ms=values['after_avg_latency_ms']-values['before_avg_latency_ms']))
    assert len(records)==270 and len(comparisons)==54
    def write_csv(path,rows):
        with path.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_csv(output/'before-after-full.csv',comparisons)
    write_csv(output/'grid-checks.csv',checks)
    (output/'laya-decisions.jsonl').write_text(''.join(json.dumps(a,ensure_ascii=False)+'\n' for a in records),encoding='utf-8')
    verification=dict(grid_runs=9,strategies_per_run=6,terminal_results=1620,laya_decisions=270,
                      failed_checks=0,scenario_checks=len(checks),maximum_time_conservation_error_ms=max_error,
                      laya_truncated_inputs=truncated,image_batch_sha256=batch)
    (output/'grid-verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
    lines=['# SimPy 修改前後比較','',
           '模型版本由 f8ec356 改為 audit-v2。原始證據均保留，不能視為相同模型條件下的演算法改善。',
           '測試圖片、順序、實測推論真值、seed=42、節點算力/RTT/頻寬、到達間隔與 Deadline 相同；本次正式結果使用 Realistic、獨立網路與 complete_all。',
           '決策從逐圖真值改為獨立校準中位數；節點狀態改為可觀測估計並納入傳輸中承諾工作，Load-threshold 門檻亦包含承諾任務。Laya 的輸入結構因此改變，真實 wall-clock 耗時也不同。',
           '', '## 九情境平均（每格相同 30 張，非統計顯著性分析）','',
           '|策略|舊平均延遲 ms|新平均延遲 ms|舊 Deadline 達成率|新 Deadline 達成率|',
           '|---|---:|---:|---:|---:|']
    for name in new['strategies']:
        rows=[r for r in comparisons if r['strategy']==name]
        lines.append(f"|{name}|{mean(r['before_avg_latency_ms'] for r in rows):.3f}|{mean(r['after_avg_latency_ms'] for r in rows):.3f}|{mean(r['before_deadline_met_rate'] for r in rows):.2%}|{mean(r['after_deadline_met_rate'] for r in rows):.2%}|")
    lines+=['','## 每情境 Latency-aware / Laya','',
            '|間隔/Deadline ms|策略|舊平均/P95 ms|新平均/P95 ms|舊→新 Deadline 達成率|',
            '|---|---|---:|---:|---:|']
    for r in comparisons:
        if r['strategy'] not in ('latency_aware','laya'):continue
        lines.append(f"|{r['interval_ms']}/{r['deadline_ms']}|{r['strategy']}|{r['before_avg_latency_ms']:.2f}/{r['before_p95_latency_ms']:.2f}|{r['after_avg_latency_ms']:.2f}/{r['after_p95_latency_ms']:.2f}|{r['before_deadline_met_rate']:.2%} → {r['after_deadline_met_rate']:.2%}|")
    lines+=['','## 解讀與完整數據','',
            '- `before-after-full.csv` 包含 54 列，每列均保存新舊平均、P95、Deadline 達成率、決策執行/排隊、網路、CPU 排隊/運算，以及三節點分配比例。',
            '- 固定策略執行真值未修改；小幅延遲差異可來自實測函式成本。Latency-aware 的變化包含資訊去洩漏與狀態修正，不能歸因單一修改。',
            '- Laya 的分配與成本變化同時受新輸入資訊與 wall-clock 主機負載影響；此輪沒有對 checkpoint 或提示做調優，沒有用 fallback 修飾結果。',
            '- 完成率與丟棄率在本九格 complete_all 下仍為 100%/0%；這是模型政策，不是策略達成 Deadline 的證據。',
            '- 共用網路與丟棄政策另有手算/單元/API 測試；本九格沒有偷換為共享模式或 drop 政策。',
            f"- 逐筆驗證 1620 筆時間守恆，最大誤差 {max_error:.3g} ms；270 次真實 Laya 原始選擇與結果一致，輸入截斷 {truncated} 次。",'']
    (output/'SIMPY_BEFORE_AFTER.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(verification))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--audit',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();analyze(a.before,a.after,a.audit,a.output)
