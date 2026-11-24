"""Paper-inspired phase-overlap latency estimate, not a LEAOT reproduction.

LEAOT III-B (2)-(6), III-C (9): queue work / speed, communication plus
execution, and remaining-deadline pressure. This project has no energy model.
All quantities below are ms or dimensionless ratios; no arbitrary weighted sum.
"""
from math import inf


def estimate_v2(task,node):
    if not node.available:return dict(total_ms=inf,slack_ms=-inf,late_ratio=inf,post_cpu_pressure=inf)
    cpu=node.queue_work_ms/node.compute_speed
    committed=node.committed_work_ms/node.compute_speed
    compute=task.estimated_workload_ms/node.compute_speed
    elapsed=max(0.,node.observed_at_ms-task.arrival_ms)
    remaining=task.deadline_ms-elapsed
    if node.name=='local':
        input_ready=0.;cpu_finish=cpu+committed+compute;total=cpu_finish;download=0.
    else:
        upload=task.image_size_mb*8000/node.bandwidth_mbps
        download=task.result_size_kb*8/node.bandwidth_mbps
        # Existing link/CPU work drains while this task propagates and uploads.
        input_ready=max(node.rtt_ms/2,node.upload_backlog_ms)+upload
        cpu_finish=max(input_ready,cpu+committed)+compute
        total=max(cpu_finish+node.rtt_ms/2,node.download_backlog_ms)+download
    return dict(total_ms=total,input_ready_ms=input_ready,cpu_finish_ms=cpu_finish,
                remaining_deadline_ms=remaining,slack_ms=remaining-total,
                late_ratio=max(0.,total-remaining)/max(task.deadline_ms,1e-9),
                post_cpu_pressure=(cpu+committed+compute)/max(remaining,1e-9))


class LatencyAwareV2Strategy:
    def __init__(self):self.last_estimates={}

    def select_node(self,task,state):
        self.last_estimates={n.name:estimate_v2(task,n) for n in state.nodes()}
        candidates=[n for n in state.nodes() if n.available]
        if not candidates:raise ValueError('No available nodes')
        # Feasibility, tardiness and latency have explicit physical meanings.
        # With latency as the sole objective the first two preserve its ordering;
        # pressure only resolves exact ties, rather than imposing unmeasured energy.
        return min(candidates,key=lambda n:(self.last_estimates[n.name]['slack_ms']<0,
                   self.last_estimates[n.name]['late_ratio'],self.last_estimates[n.name]['total_ms'],
                   self.last_estimates[n.name]['post_cpu_pressure'],n.name)).name
