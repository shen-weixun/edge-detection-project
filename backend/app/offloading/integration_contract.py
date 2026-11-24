"""Additive team contract helpers; no RL algorithm or environment changes.

Only observable DTOs enter the optional feature-vector/action adapter. The
standard Simulator and metric definitions are reused for external policies.
"""
from dataclasses import asdict,fields
from math import isfinite
from .models import DecisionTask,NodeState,SystemState
from .simulator import Simulator
from .experiment import metrics
TASK_FEATURES=tuple(f.name for f in fields(DecisionTask) if f.name!='task_id')
NODE_FEATURES=tuple(f.name for f in fields(NodeState) if f.name!='name')
FEATURE_NAMES=TASK_FEATURES+tuple(n+'.'+f for n in ('local','edge','cloud') for f in NODE_FEATURES)
ACTIONS=('local','edge','cloud')

def decision_request(task,state):
 if not isinstance(task,DecisionTask) or not isinstance(state,SystemState):raise TypeError('Observable DecisionTask and SystemState required')
 return dict(schema='offloading-decision-v1',task=asdict(task),nodes=[asdict(n) for n in state.nodes()])

def feature_vector(task,state):
 decision_request(task,state)
 if tuple(n.name for n in state.nodes())!=ACTIONS:raise ValueError('Canonical local/edge/cloud state order required')
 v=tuple(float(getattr(task,f)) for f in TASK_FEATURES)+tuple(float(getattr(n,f)) for n in state.nodes() for f in NODE_FEATURES)
 if not all(isfinite(x) for x in v):raise ValueError('Finite features required')
 return v

class IndexPolicy:
 """Adapt an externally supplied callable(vector)->0/1/2 without training it."""
 def __init__(self,select_action):self.select_action=select_action
 def select_node(self,task,state):
  action=self.select_action(feature_vector(task,state))
  if type(action) is not int or not 0<=action<3:raise ValueError('Action must be Python int 0/1/2')
  if not state.nodes()[action].available:raise ValueError('Selected node unavailable')
  return ACTIONS[action]

def run_policy(tasks,policy,**config):
 if config.get('information_mode','realistic')!='realistic':raise ValueError('Team evaluation requires realistic information')
 sim=Simulator(tasks,policy,**config);rows=sim.run()
 return dict(summary=metrics(rows),tasks=rows,node_statistics=sim.node_statistics(),queue_samples=sim.queue_samples,events=sim.events)

def validate_manifest_split(rows):
 """Group/content/path guard in addition to the existing two-way EpisodeSplit."""
 for field in ('source_path','image_sha256','group'):
  seen={}
  for r in rows:
   if r.get('role') not in ('training','validation','testing') or not r.get(field):raise ValueError('Complete three-way split fields required')
   if r[field] in seen and seen[r[field]]!=r['role']:raise ValueError('Cross-split '+field+' overlap')
   seen[r[field]]=r['role']
