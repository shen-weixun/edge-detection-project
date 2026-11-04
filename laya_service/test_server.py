import unittest,tempfile,os
from unittest.mock import patch
from pathlib import Path
import json
import server

class ProtocolTests(unittest.TestCase):
    def state(self):
        task=dict(task_id=0,image_size_mb=1,width=100,height=100,arrival_ms=0,deadline_ms=500,estimated_workload_ms=100,result_size_kb=16)
        nodes=[dict(name=n,compute_speed=2,queue_work_ms=40,bandwidth_mbps=80,rtt_ms=20,observed_at_ms=10) for n in ['cloud','local','edge']]
        return task,nodes

    def test_compact_preserves_order_and_neutral_options(self):
        task,nodes=self.state();state=server.compact_state(task,nodes)
        self.assertEqual([n['node'] for n in state['candidates']],['cloud','local','edge'])
        self.assertEqual(list(server.neutral_questions(nodes)['offload_target']['criteria']),['cloud','local','edge'])
        self.assertEqual(state['candidates'][0]['compute_ms'],50)
        self.assertEqual(state['candidates'][0]['input_transfer_ms'],110)
        self.assertEqual(state['remaining_deadline_ms'],490)
        self.assertNotIn('faster',json.dumps(server.neutral_questions(nodes)))

    def test_legacy_unchanged_and_v2_returns_raw_choice_with_thread_restore(self):
        import torch
        task,nodes=self.state();calls=[]
        class Fake:
            def predict(self,s,q,**kw):calls.append((s,q,kw));return dict(answers={'offload_target':dict(choice='cloud',confidence=.1)},routing={'model':'multilingual'},usage={'truncated':False})
        previous=torch.get_num_threads()
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'LAYA_AUDIT_ROOT':d}),patch.object(server,'_router',Fake()):
            for variant in ['legacy','v2']:
                result=server.decide(server.DecisionRequest(task=task,nodes=nodes,variant=variant))
                self.assertEqual(result['node'],'cloud')
            self.assertEqual(calls[0][0],dict(task=task,nodes=nodes));self.assertEqual(calls[0][2],{})
            self.assertEqual(calls[1][2],{'model':'multilingual'})
            rows=[json.loads(x) for x in (Path(d)/'decisions.jsonl').read_text().splitlines()]
            self.assertEqual([r['variant'] for r in rows],['legacy','v2'])
        self.assertEqual(torch.get_num_threads(),previous)
