"""Frozen controlled scenarios shared by the V2 tests and evaluation runner."""
from dataclasses import replace
from app.offloading.models import Task,NodeConfig
from app.offloading.simulator import DEFAULT_NODES
from acceptance_reference import scenarios


def paper_cases():
    task,advantage=scenarios();cases=[]
    for name,nodes in advantage.items():cases.append(dict(name=name,tasks=[task],nodes=nodes,forced_prefix={}))
    cases += [
      dict(name='edge_cpu_backlog',tasks=[Task(0,.001,1,6000,0,10000,estimated_workload_ms=6000),replace(task,task_id=1,arrival_ms=20)],nodes=DEFAULT_NODES,forced_prefix={0:'edge'}),
      dict(name='cloud_link_backlog',tasks=[Task(0,5,1,600,0,10000,estimated_workload_ms=600),replace(task,task_id=1,arrival_ms=60)],nodes=DEFAULT_NODES,forced_prefix={0:'cloud'}),
      dict(name='short_deadline',tasks=[replace(task,deadline_ms=100)],nodes=advantage['B_edge'],forced_prefix={}),
      dict(name='burst',tasks=[replace(task,task_id=i,image_size_mb=.1,arrival_ms=0,deadline_ms=500) for i in range(6)],nodes=DEFAULT_NODES,forced_prefix={}),
      dict(name='large_underestimate',tasks=[replace(task,workload_ms=6000,estimated_workload_ms=100,deadline_ms=1000)],nodes=DEFAULT_NODES,forced_prefix={}),
      dict(name='cpu_transfer_overlap',tasks=[Task(0,.001,1,600,0,10000,estimated_workload_ms=600),replace(task,task_id=1,arrival_ms=20,workload_ms=600)],nodes=dict(local=NodeConfig(1,0,1000),edge=NodeConfig(3,0,80),cloud=NodeConfig(8,250,100)),forced_prefix={0:'edge'})]
    return cases
