import unittest
from copy import deepcopy
from dataclasses import replace
import numpy as np

from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.integral_env import IntegralEnv
from app.offloading.agents49.evaluation import evaluation_snapshot
from app.offloading.integration_contract import feature_vector, run_policy
from app.offloading.models import Task, NodeConfig
from app.offloading.rl import OffloadingEnv


def workload(n=90):
    return [Task(i,.001,1,20+i%5,i*3.,50,estimated_workload_ms=22) for i in range(n)]


def train_with_validation(cls, insert):
    agent=cls(seed=73,gamma=1)
    env=IntegralEnv(workload())
    observation=env.reset()
    steps=0
    while observation is not None:
        f=feature_vector(*observation)
        action=agent.act(f,epsilon=.4)
        nxt,r,done,info=env.step(action)
        agent.remember(f,action,r,f if done else feature_vector(*nxt),done)
        agent.train_step()
        if insert:
            frozen=evaluation_snapshot(agent,919)
            frozen.rng=np.random.default_rng(919)
            class Policy:
                def select_node(self,task,state):
                    return ("local","edge","cloud")[frozen.act(feature_vector(task,state),epsilon=.1)]
            run_policy(workload(5),Policy(),include_decision_overhead=False)
        observation=nxt
        steps+=1
    return agent


class IntegralRLTests(unittest.TestCase):
    def test_greedy_does_not_consume_rng(self):
        for cls in (DQN,DDQN):
            a=cls(seed=11)
            env=IntegralEnv(workload(1))
            f=feature_vector(*env.reset())
            before=deepcopy(a.rng.bit_generator.state)
            for _ in range(10):
                a.act(f,epsilon=0)
            self.assertEqual(before,a.rng.bit_generator.state)

    def test_inserted_validation_preserves_training_weights_and_rng(self):
        for cls in (DQN,DDQN):
            a,b=train_with_validation(cls,False),train_with_validation(cls,True)
            self.assertEqual(a.updates,b.updates)
            self.assertEqual(a.rng.bit_generator.state,b.rng.bit_generator.state)
            for x,y in zip(a.online+a.target,b.online+b.target):
                np.testing.assert_array_equal(x,y)

    def test_out_of_order_and_drain(self):
        a=Task(0,.001,1,300,0,100)
        work=[a,replace(a,task_id=1,arrival_ms=1,workload_ms=1),
              replace(a,task_id=2,arrival_ms=50,workload_ms=1)]
        env=IntegralEnv(work)
        env.reset()
        records=[]
        for action in (0,1,2):
            records.append(env.step(action))
        self.assertEqual([r[3]["task_done_ids"] for r in records],[[],[1],[2,0]])
        self.assertEqual([r[2] for r in records],[False,False,True])
        self.assertIsNone(records[-1][0])
        rows=env.sim.results
        self.assertAlmostEqual(-sum(r[1] for r in records),
                               sum(r["total_latency_ms"]/1000+(not r["deadline_met"]) for r in rows))
        self.assertEqual(sum(r[3]["new_misses"] for r in records),
                         sum(not r["deadline_met"] for r in rows))
        self.assertFalse(env.sim.active_ids)
        self.assertTrue(all(r[3]["delta_area_ms"]>=0 for r in records))

    def test_irregular_intervals_known_integral(self):
        work=[Task(0,.001,1,10,0,100),Task(1,.001,1,5,2,100),Task(2,.001,1,2,30,100)]
        env=IntegralEnv(work)
        env.reset()
        rewards=[]
        while not env.done:
            _,r,_,_=env.step(0)
            rewards.append(r)
        # [0,2]:1*2; [2,10]:2*8; [10,15]:1*5; [15,30]:0; [30,32]:1*2
        self.assertAlmostEqual(env.sim.area_ms,25)
        self.assertAlmostEqual(-sum(rewards),.025)

    def test_simultaneous_completion_once(self):
        nodes={n:NodeConfig(1,0,1000) for n in ("local","edge","cloud")}
        work=[Task(i,.001,1,100 if i==0 else 99.984,0,50,result_size_kb=1) for i in range(3)]
        env=IntegralEnv(work,nodes=nodes)
        env.reset()
        total=0
        for action in (0,1,2):
            _,r,_,_=env.step(action)
            total+=r
        self.assertAlmostEqual(env.sim.area_ms,300)
        self.assertEqual(env.sim.misses,3)
        self.assertAlmostEqual(total,-3.3)
        self.assertEqual(len(env.sim.settled_ids),3)

    def test_unrevealed_work_does_not_change_early_reward_or_state(self):
        states=[]
        for actual in (100,300):
            env=IntegralEnv([Task(0,.001,1,actual,0,1000,estimated_workload_ms=150),
                             Task(1,.001,1,10,5,1000,estimated_workload_ms=150)])
            env.reset()
            obs,r,done,info=env.step(0)
            self.assertFalse(done)
            self.assertEqual(info["task_done_ids"],[])
            self.assertAlmostEqual(r,-.005)
            states.append(feature_vector(*obs))
        self.assertEqual(states[0],states[1])

    def test_native_next_observation(self):
        a,b=IntegralEnv(workload(4)),OffloadingEnv(workload(4))
        x,y=a.reset(),b.reset()
        self.assertEqual(feature_vector(*x),feature_vector(*y))
        for action in (0,1,2,0):
            x,_,dx,_=a.step(action)
            y,_,dy,_=b.step(action)
            self.assertEqual(dx,dy)
            if not dx:
                self.assertEqual(feature_vector(*x),feature_vector(*y))

    def test_nonzero_bootstrap_targets_differ(self):
        d,q=DQN(gamma=1),DDQN(gamma=1)
        # Online argmax=0, Target argmax=1.
        for agent in (d,q):
            for w in agent.online+agent.target:
                w.fill(0)
            agent.online[-1][:]=[3,1,0]
            agent.target[-1][:]=[1,4,0]
        x=np.zeros((1,49))
        masks=np.ones((1,3))
        self.assertEqual(d._next_q(x,masks)[0],4)
        self.assertEqual(q._next_q(x,masks)[0],1)

