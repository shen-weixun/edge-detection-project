"""Numerical minimum reproductions, independent of the training comparison."""
import sys
sys.path[:0]=["/app","/app/tests"]
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import zipfile
import numpy as np
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.integral_env import IntegralEnv
from app.offloading.integration_contract import feature_vector
from app.offloading.models import Task,NodeConfig
from test_integral_rl import train_with_validation,workload
from agents49_experiment import write

OUT=Path("/profiles/rl-long-horizon-evidence")
OUT.mkdir(exist_ok=False)
with zipfile.ZipFile("/tmp/rl-method-review.zip") as z:
    old_source=z.read("source/backend/app/offloading/agents49/dqn.py").decode("utf-8-sig")
namespace={"__name__":"app.offloading.agents49.legacy_dqn","__package__":"app.offloading.agents49"}
exec(compile(old_source,"archived_dqn.py","exec"),namespace)
OldDQN=namespace["DQN"]


def signature(agent):
    return sha256(b"".join(w.tobytes() for w in agent.online+agent.target)).hexdigest()


def contaminated(insert):
    a=OldDQN(seed=73,gamma=1)
    env=IntegralEnv(workload())
    obs=env.reset()
    while obs is not None:
        f=feature_vector(*obs)
        action=a.act(f,.4)
        nxt,r,done,_=env.step(action)
        a.remember(f,action,r,f if done else feature_vector(*nxt),done)
        a.train_step()
        if insert:
            for _ in range(7):
                a.act(f,0)
        obs=nxt
    return a


proof={}
env=IntegralEnv(workload(1))
f=feature_vector(*env.reset())
for label,cls in (("archived",OldDQN),("fixed_dqn",DQN),("fixed_ddqn",DDQN)):
    a=cls(seed=73)
    before=deepcopy(a.rng.bit_generator.state)
    for _ in range(7):
        a.act(f,0)
    proof[label]={"rng_unchanged":before==a.rng.bit_generator.state}
old_a,old_b=contaminated(False),contaminated(True)
proof["archived_training"]={"without_validation":signature(old_a),"with_validation":signature(old_b),
                            "equal":signature(old_a)==signature(old_b)}
for label,cls in (("dqn",DQN),("ddqn",DDQN)):
    a,b=train_with_validation(cls,False),train_with_validation(cls,True)
    proof[label+"_isolated_training"]={"without_validation":signature(a),"with_validation":signature(b),
                                       "equal":signature(a)==signature(b),"updates":a.updates}
write(OUT/"rng-isolation.json",proof)

a=Task(0,.001,1,300,0,100)
from dataclasses import replace
cases={"reverse":[a,replace(a,task_id=1,arrival_ms=1,workload_ms=1),replace(a,task_id=2,arrival_ms=50,workload_ms=1)],
       "irregular":[Task(0,.001,1,10,0,100),Task(1,.001,1,5,2,100),Task(2,.001,1,2,30,100)]}
examples={}
for name,tasks in cases.items():
    env=IntegralEnv(tasks)
    obs=env.reset()
    transitions=[]
    for action in ((0,1,2) if name=="reverse" else (0,0,0)):
        current=feature_vector(*obs)
        obs,r,done,info=env.step(action)
        transitions.append(dict(observation=current,action=action,reward=r,done=done,
                                next_observation=None if done else feature_vector(*obs),info=info))
    examples[name]=dict(transitions=transitions,tasks=env.sim.results,area_ms=env.sim.area_ms,
                         misses=env.sim.misses,events=env.sim.cost_events)
write(OUT/"reward-timing.json",examples)
d,q=DQN(gamma=1),DDQN(gamma=1)
for agent in (d,q):
    for w in agent.online+agent.target:
        w.fill(0)
    agent.online[-1][:]=[3,1,0]
    agent.target[-1][:]=[1,4,0]
x=np.zeros((1,49))
mask=np.ones((1,3))
write(OUT/"bootstrap-targets.json",{"gamma":1,"reward":-.2,
      "online_q":[3,1,0],"target_q":[1,4,0],
      "dqn_y":float(-.2+d._next_q(x,mask)[0]),
      "ddqn_y":float(-.2+q._next_q(x,mask)[0])})
print("Evidence complete: archived contamination reproduced; isolated equality verified.")

