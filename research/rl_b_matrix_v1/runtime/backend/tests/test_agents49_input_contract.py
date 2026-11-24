"""P0-01 contract regression tests; only temporary synthetic fixtures, no training runs."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from app.offloading.agents49.adapter import Agent49Policy, load_agent
from app.offloading.agents49.dqn import DQN
from app.offloading.agents49.ddqn import DDQN
from app.offloading.agents49.input_contract import (
    InputSpec, InputContractError, ContractRef, prepare_state, greedy_action,
    export_agent_contract, write_contract_index, file_sha256, canonical_bytes,
)
from app.offloading.agents49.normalizer import normalize


DROP = (3, 4, 5, 6, 7, 10, 11, 12, 13, 16, 17, 18, 19, 20, 31, 34, 36, 45, 48)


def raw_state():
    x = np.arange(1, 50, dtype=float)
    x[[14, 28, 42]] = 1
    return x


class InputContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.getenv('P0_TMP'))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'training-source.py'
        self.source.write_text('synthetic fixture; explicit InputSpec\n', encoding='utf-8')

    def fixture(self, spec=InputSpec(), constructor=DQN):
        agent = constructor(input_spec=spec)
        path = self.root/(agent.algorithm+'-'+spec.feature_mode+'.npz')
        agent.save(path)
        ref = export_agent_contract(agent, path, self.root/'contracts', [self.source])
        return agent, path, ref

    def rewrite(self, ref, change):
        doc = json.loads(ref.path.read_text())
        change(doc)
        path = self.root/'changed.json'
        path.write_bytes(canonical_bytes(doc))
        return ContractRef(path, file_sha256(path), ref.source_root)

    def test_full_and_pruned_use_original_normalizer_once(self):
        raw = raw_state()
        for spec in (InputSpec(), InputSpec('pruned', DROP)):
            with self.subTest(mode=spec.feature_mode):
                expected = raw.copy(); expected[list(spec.zeroed_feature_indices)] = 0
                with patch('app.offloading.agents49.input_contract.normalize', wraps=normalize) as spy:
                    p = prepare_state(raw, spec)
                    self.assertEqual(spy.call_count, 1)
                np.testing.assert_array_equal(p.masked, expected)
                np.testing.assert_array_equal(p.normalized, normalize(expected))
                np.testing.assert_array_equal(raw, raw_state())
                self.assertEqual(p.available_actions, (0, 1, 2))

    def test_three_paths_and_current_next_replay(self):
        for ctor in (DQN, DDQN):
            for spec in (InputSpec(), InputSpec('pruned', DROP)):
                with self.subTest(algorithm=ctor.algorithm, mode=spec.feature_mode):
                    original, path, ref = self.fixture(spec, ctor)
                    agent = load_agent(ctor.algorithm, path, file_sha256(path), contract_ref=ref)
                    raw = raw_state(); nxt = raw*2; nxt[[14,28,42]] = [0,1,0]
                    p, q, action = original.predict_greedy(raw)
                    policy = Agent49Policy(agent)
                    self.assertEqual(agent.act(raw, epsilon=0), action)
                    self.assertEqual(policy.choose(raw), action)
                    np.testing.assert_array_equal(policy.decisions[-1]['masked_features'], p.masked)
                    np.testing.assert_array_equal(policy.decisions[-1]['normalized_features'], p.normalized)
                    np.testing.assert_array_equal(policy.decisions[-1]['q_values'], q)
                    for done in (False, True):
                        agent.remember(raw, action, -.25, nxt, done)
                        s,a,r,ns,d,m = agent.memory[-1]
                        np.testing.assert_array_equal(s, p.normalized)
                        np.testing.assert_array_equal(ns, prepare_state(nxt,spec).normalized)
                        np.testing.assert_array_equal(m, [0,1,0])
                        self.assertEqual((a,r,d),(action,-.25,done))

    def test_act_and_adapter_normalize_once_replay_twice(self):
        agent = DQN(input_spec=InputSpec('pruned', DROP)); raw = raw_state()
        with patch('app.offloading.agents49.input_contract.normalize', wraps=normalize) as spy:
            action=agent.act(raw); self.assertEqual(spy.call_count,1)
            Agent49Policy(agent).choose(raw); self.assertEqual(spy.call_count,2)
            agent.remember(raw,action,0,raw); self.assertEqual(spy.call_count,4)

    def test_illegal_action_filter_and_canonical_ties(self):
        for spec in (InputSpec(), InputSpec('pruned', DROP)):
            agent=DQN(input_spec=spec); raw=raw_state()
            for flags,q,expected in [([0,1,1],[10,5,1],1),([1,1,0],[1,5,10],1),
                                      ([0,0,1],[99,99,-1],2),([1,1,1],[7,7,7],0),
                                      ([0,1,1],[7,7,7],1)]:
                raw[[14,28,42]]=flags
                with patch.object(agent,'_forward',return_value=(None,None,np.array([q],dtype=float))):
                    self.assertEqual(agent.act(raw),expected)
                    self.assertEqual(Agent49Policy(agent).choose(raw),expected)
            raw[[14,28,42]]=0
            with self.assertRaises(InputContractError):agent.act(raw)

    def test_no_rng_or_weight_mutation_during_greedy_inference(self):
        agent=DQN(input_spec=InputSpec('pruned', DROP)); before=deepcopy(agent.rng.bit_generator.state)
        weights=[x.copy() for x in agent.online]
        agent.act(raw_state(),epsilon=0); Agent49Policy(agent).choose(raw_state())
        self.assertEqual(before,agent.rng.bit_generator.state)
        for a,b in zip(weights,agent.online):np.testing.assert_array_equal(a,b)

    def test_missing_contract_rejected_by_both_loaders(self):
        _,path,ref=self.fixture()
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path))
        with self.assertRaises(InputContractError):DQN().load(path)
        missing=replace(ref,path=self.root/'missing.json')
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=missing)

    def test_metadata_sha_and_checkpoint_sha_must_match(self):
        _,path,ref=self.fixture()
        for digest,binding in [('0'*64,ref),(file_sha256(path),replace(ref,sha256='0'*64))]:
            with self.assertRaises(InputContractError):load_agent('dqn',path,digest,contract_ref=binding)

    def test_model_schema_algorithm_and_required_fields(self):
        _,path,ref=self.fixture()
        changes=[lambda d:d.pop('sources'),lambda d:d.update(schema='unknown'),
                 lambda d:d.update(algorithm='ddqn'),lambda d:d.update(sources=[]),
                 lambda d:d.update(mask_evidence={})]
        for change in changes:
            changed=self.rewrite(ref,change)
            with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=changed)

    def test_feature_order_normalizer_and_action_contract_rejected(self):
        _,path,ref=self.fixture()
        def swapped(d):
            names=d['input_spec']['feature_names'];names[0],names[1]=names[1],names[0]
        changes=[swapped,lambda d:d['input_spec'].update(schema='unknown'),
                 lambda d:d['input_spec']['normalizer'].update(version='other'),
                 lambda d:d['input_spec']['normalizer']['scales'].__setitem__(0,6),
                 lambda d:d['input_spec']['normalizer'].update(binary_indices=[14,28]),
                 lambda d:d['input_spec'].update(action_mapping=['edge','local','cloud']),
                 lambda d:d['input_spec'].pop('zeroed_feature_indices')]
        for change in changes:
            changed=self.rewrite(ref,change)
            with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=changed)

    def test_invalid_masks_and_full_pruned_contradictions(self):
        for mode,drop in [('full',(3,)),('pruned',()),('pruned',(-1,)),('pruned',(49,)),
                          ('pruned',(3,3)),('pruned',(4,3)),('pruned',(3.,)),('pruned',(True,)),
                          ('pruned',(14,)),('pruned',(28,)),('pruned',(42,))]:
            with self.subTest(mode=mode,drop=drop),self.assertRaises(InputContractError):InputSpec(mode,drop)

    def test_mask_must_match_original_metadata_not_just_be_valid(self):
        _,path,ref=self.fixture(InputSpec('pruned',DROP))
        changed=self.rewrite(ref,lambda d:d.update(input_spec=InputSpec('pruned',(3,)).to_dict()))
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=changed)

    def test_changed_historical_evidence_rejected(self):
        _,path,ref=self.fixture()
        self.source.write_text('changed',encoding='utf-8')
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=ref)

    def test_metadata_cannot_be_borrowed_from_another_checkpoint(self):
        _,path,ref=self.fixture(InputSpec('pruned',DROP))
        other=self.root/'other-model.json'
        other.write_text(json.dumps(dict(sha256='0'*64,algorithm='dqn',feature_mask=list(DROP))))
        def hybrid(doc):
            relative=other.relative_to(ref.source_root).as_posix()
            doc['sources'].append(dict(path=relative,sha256=file_sha256(other)))
            doc['mask_evidence']=dict(path=relative,field='feature_mask')
        changed=self.rewrite(ref,hybrid)
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=changed)
        def wrong_binding(doc):
            relative=other.relative_to(ref.source_root).as_posix()
            doc['sources'].append(dict(path=relative,sha256=file_sha256(other)))
            doc['checkpoint_evidence']=dict(path=relative,field_path=['sha256'])
        changed=self.rewrite(ref,wrong_binding)
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_ref=changed)

    def test_model_spec_cannot_be_replaced_after_binding(self):
        agent,path,ref=self.fixture()
        agent=load_agent('dqn',path,file_sha256(path),contract_ref=ref)
        with self.assertRaises(AttributeError):agent.input_spec=InputSpec('pruned',DROP)

    def test_invalid_original_weight_archive_is_rejected(self):
        agent,path,ref=self.fixture()
        with np.load(path,allow_pickle=False) as source:original={k:source[k].copy() for k in source.files}
        for case in ('shape','dtype','nonfinite','version','extra'):
            archive={k:v.copy() for k,v in original.items()}
            if case=='shape':archive['w0']=archive['w0'][:48]
            elif case=='dtype':archive['w0']=archive['w0'].astype(np.int32)
            elif case=='nonfinite':archive['w0'][0,0]=np.nan
            elif case=='version':archive['contract']=np.array('unknown')
            else:archive['unexpected']=np.zeros(1)
            bad=self.root/(case+'.npz');np.savez(bad,**archive)
            binding=export_agent_contract(agent,bad,self.root/('contract-'+case),[self.source])
            with self.subTest(case=case),self.assertRaises(InputContractError):
                load_agent('dqn',bad,file_sha256(bad),contract_ref=binding)

    def test_invalid_raw_values_rejected_before_feature_mask(self):
        spec=InputSpec('pruned',DROP)
        for value in (float('nan'),float('inf'),-1):
            raw=raw_state();raw[3]=value
            with self.assertRaises(InputContractError):prepare_state(raw,spec)
        for raw in (np.ones(48),np.ones(50)):
            with self.assertRaises(InputContractError):prepare_state(raw,spec)
        raw=raw_state();raw[14]=.5
        with self.assertRaises(InputContractError):prepare_state(raw,spec)

    def test_index_required_and_unknown_or_duplicate_models_rejected(self):
        _,path,ref=self.fixture();index=self.root/'index.json';write_contract_index(index,[ref])
        agent=load_agent('dqn',path,file_sha256(path),contract_index=index)
        self.assertEqual(agent.input_spec,InputSpec())
        doc=json.loads(index.read_text());doc['models']*=2;index.write_bytes(canonical_bytes(doc))
        with self.assertRaises(InputContractError):load_agent('dqn',path,file_sha256(path),contract_index=index)

    def test_contract_and_index_export_never_overwrite(self):
        agent,path,ref=self.fixture();index=self.root/'index.json';write_contract_index(index,[ref])
        with self.assertRaises(FileExistsError):write_contract_index(index,[ref])
        doc=json.loads(ref.path.read_text());doc['algorithm']='ddqn';ref.path.write_bytes(canonical_bytes(doc))
        with self.assertRaises(InputContractError):export_agent_contract(agent,path,self.root/'contracts',[self.source])


if __name__ == '__main__':
    unittest.main()
