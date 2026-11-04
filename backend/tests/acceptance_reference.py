"""Independent arithmetic/FCFS reference for complete_all, zero decision cost.

No imports from simulator or policy cost functions. Service calendars are built
in three offline passes: uploads, per-node CPU, downloads. This is an outcome
oracle used only in tests AFTER policy choices, never as decision information.
"""
from collections import defaultdict
from dataclasses import asdict
from app.offloading.models import Task, NodeConfig


def scenarios():
    # Historical controlled prior 600 ms; current hidden actual duration 480 ms.
    task=Task(0,1,9,480,0,5000,width=1000,height=1000,estimated_workload_ms=600)
    return task, {
      'A_local':dict(local=NodeConfig(1,0,1000),edge=NodeConfig(3,1000,1),cloud=NodeConfig(8,2000,.5)),
      'B_edge':dict(local=NodeConfig(1,0,1000),edge=NodeConfig(6,4,1000),cloud=NodeConfig(8,2000,1)),
      'C_cloud':dict(local=NodeConfig(1,0,1000),edge=NodeConfig(2,30,80),cloud=NodeConfig(20,2,1000)),
    }


def single_cost(task,cfg,node,estimated=False,bw=None):
    work=task.estimated_workload_ms if estimated else task.workload_ms
    network=0 if node=='local' else cfg.rtt_ms+8000*task.image_size_mb/(bw or cfg.bandwidth_mbps)+8*task.result_size_kb/(bw or cfg.bandwidth_mbps)
    return dict(network_ms=network,compute_ms=work/cfg.speed,queue_ms=0.,total_latency_ms=network+work/cfg.speed)


def reference(tasks,placements,nodes,mode='independent',shared_bw=120):
    out={};links=defaultdict(list);cpu=defaultdict(list);downloads=defaultdict(list)
    for t in tasks:
        name=placements[t.task_id];cfg=nodes[name]
        r=dict(task_id=t.task_id,node=name,arrival=t.arrival_ms,upload_queue_ms=0.,download_queue_ms=0.,upload_ms=0.,download_ms=0.)
        out[t.task_id]=r
        if name=='local':cpu[name].append((t.arrival_ms,t.task_id,t));continue
        bw=min(cfg.bandwidth_mbps,shared_bw) if mode=='shared' else cfg.bandwidth_mbps
        r.update(upload_ms=8000*t.image_size_mb/bw,download_ms=8*t.result_size_kb/bw)
        links['shared' if mode=='shared' else name].append((t.arrival_ms+cfg.rtt_ms/2,t.task_id,t))
    calendars={}
    for key,jobs in links.items():
        free=0.;intervals=[]
        for ready,tid,t in sorted(jobs):
            r=out[tid];start=max(ready,free);free=start+r['upload_ms']
            r.update(upload_queue_ms=start-ready,upload_started=start,upload_completed=free)
            intervals.append((start,free,tid));cpu[r['node']].append((free,tid,t))
        calendars['upload/'+key]=intervals
    for name,jobs in cpu.items():
        free=0.;intervals=[]
        for ready,tid,t in sorted(jobs):
            r=out[tid];cfg=nodes[name];start=max(ready,free);free=start+t.workload_ms/cfg.speed
            r.update(cpu_ready=ready,cpu_started_at_ms=start,cpu_completed_at_ms=free,queue_ms=start-ready,compute_ms=free-start)
            intervals.append((start,free,tid))
            if name=='local':r['completed_at_ms']=free
            else:downloads['shared' if mode=='shared' else name].append((free+cfg.rtt_ms/2,tid,t))
        calendars['cpu/'+name]=intervals
    for key,jobs in downloads.items():
        free=0.;intervals=[]
        for ready,tid,t in sorted(jobs):
            r=out[tid];start=max(ready,free);free=start+r['download_ms']
            r.update(download_queue_ms=start-ready,download_started=start,completed_at_ms=free)
            intervals.append((start,free,tid))
        calendars['download/'+key]=intervals
    for t in tasks:
        r=out[t.task_id];r['total_latency_ms']=r['completed_at_ms']-t.arrival_ms
        r['network_ms']=r['upload_ms']+r['download_ms']+r['upload_queue_ms']+r['download_queue_ms']+(0 if r['node']=='local' else nodes[r['node']].rtt_ms)
    return out,calendars


def check_run(sim,rows,tolerance=1e-7):
    assert len(rows)==len(sim.tasks)==len({r['task_id'] for r in rows})
    placements={r['task_id']:r['selected_node'] for r in rows}
    nodes={name:n.cfg for name,n in sim.nodes.items()}
    ref,calendars=reference(sim.tasks,placements,nodes,sim.network_mode,sim.shared_bandwidth_mbps)
    max_error=0
    for r in rows:
        assert r['completed'] and not r['dropped']
        assert r['decision_ms']==r['decision_queue_ms']==0
        assert all(r[k]>=0 for k in ('network_ms','queue_ms','compute_ms','total_latency_ms','arrival_ms'))
        assert r['arrival_ms']<=r['cpu_started_at_ms']<=r['cpu_completed_at_ms']<=r['completed_at_ms']
        assert abs(r['total_latency_ms']-sum(r[k] for k in ('network_ms','queue_ms','compute_ms','decision_ms','decision_queue_ms')))<tolerance
        for key in ('cpu_started_at_ms','cpu_completed_at_ms','completed_at_ms','queue_ms','compute_ms','network_ms','total_latency_ms'):
            err=abs(r[key]-ref[r['task_id']][key]);max_error=max(max_error,err)
            assert err<tolerance,(r['task_id'],key,r[key],ref[r['task_id']][key])
    for resource,intervals in calendars.items():
        for a,b in zip(intervals,intervals[1:]):assert a[1]<=b[0]+tolerance,(resource,a,b)
    horizon=max((r['completed_at_ms'] for r in rows),default=0)
    for name,node in sim.nodes.items():
        assert node.cpu.capacity==1 and node.cpu.count==0 and not node.jobs
        assert node.upload.resource.capacity==node.download.resource.capacity==1
        assert not node.upload.pending and not node.download.pending
        own=[r for r in rows if r['selected_node']==name]
        stats=sim.node_statistics()[name]
        area=sum(r['queue_ms'] for r in own)
        assert abs(stats['mean_queue_time_weighted']-(area/horizon if horizon else 0))<tolerance
        assert 0<=stats['cpu_utilization']<=1+tolerance
    for tid in placements:
        events=[e for e in sim.events if e['task_id']==tid]
        assert all(a['time_ms']<=b['time_ms'] for a,b in zip(events,events[1:]))
        assert events[-1]['stage'] is None
    return dict(max_reference_error_ms=max_error,reference=ref,resource_calendars=calendars)
