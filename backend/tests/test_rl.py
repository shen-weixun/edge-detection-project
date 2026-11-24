import unittest
from app.offloading.rl import OffloadingEnv
from app.offloading.models import Task
from app.offloading.simulator import Simulator
from app.offloading.strategies import FixedStrategy

class RLValidation(unittest.TestCase):
    def test_action_next_state_delayed_reward_done_reset(self):
        tasks=[Task(i,1,1,100,i*10,1000) for i in range(3)]
        env=OffloadingEnv(tasks)
        first=env.reset()
        self.assertEqual(first[0].task_id,0)
        obs,reward,done,info=env.step(0)
        self.assertEqual(obs[0].task_id,1);self.assertEqual(reward,0);self.assertFalse(done)
        self.assertEqual(obs[1].local.cpu_running,1)
        obs,_,done,_=env.step(0)
        self.assertEqual(obs[0].task_id,2);self.assertFalse(done)
        obs,reward,done,info=env.step(0)
        self.assertTrue(done);self.assertIsNone(obs)
        self.assertEqual(len(info['terminal_rewards']),3)
        self.assertAlmostEqual(reward,-.57)
        reference=Simulator(tasks,FixedStrategy('local'),include_decision_overhead=False).run()
        self.assertEqual([r['completed_at_ms'] for r in env.sim.results],[r['completed_at_ms'] for r in reference])
        old=env.sim
        self.assertEqual(env.reset(),first)
        self.assertIsNot(env.sim.env,old.env)
        self.assertEqual(env.sim.results,[])
        with self.assertRaises(ValueError):env.step(3)
        with self.assertRaises(ValueError):env.step(-1)

    def test_training_adapter_cannot_claim_decision_overhead(self):
        with self.assertRaises(ValueError):OffloadingEnv([],include_decision_overhead=True)

    def test_training_test_episode_split(self):
        from dataclasses import replace
        from app.offloading.rl import EpisodeSplit
        train=Task(0,1,1,100,0,1000,source_path='lfw/train.jpg',dataset='lfw')
        test=replace(train,source_path='lfw/test.jpg')
        split=EpisodeSplit((train,),(test,))
        a=split.make_env('training');b=split.make_env('testing')
        self.assertEqual(a.reset()[0].estimated_workload_ms,150)
        self.assertEqual(b.reset()[0].estimated_workload_ms,150)
        self.assertIsNot(a.sim.env,b.sim.env)
        with self.assertRaises(ValueError):EpisodeSplit((train,),(train,))
        with self.assertRaises(ValueError):split.make_env('invalid')
