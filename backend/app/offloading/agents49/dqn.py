"""純 NumPy DQN：49 維觀測，3 動作。支援非同步 SimPy 奬勵回傳。"""
from collections import deque
from pathlib import Path
import json
import numpy as np
from .normalizer import CONTRACT_VERSION
from .input_contract import (InputSpec, InputContractError, prepare_state, greedy_action,
                             validate_model_contract, contract_from_index, WEIGHT_SHAPES)


class DQN:
    algorithm = 'dqn'

    def __init__(self, state_size=49, hidden=64, actions=3, lr=0.0003,
                 gamma=0.99, batch_size=64, seed=42, target_interval=200, *, input_spec=None):
        if state_size != 49 or actions != 3:
            raise ValueError('此版本固定 49 維狀態與 3 動作')
        self.rng = np.random.default_rng(seed)
        self.lr, self.gamma, self.batch_size = lr, gamma, batch_size
        self.target_interval = target_interval
        self.online = self._init_weights(state_size, hidden, actions)
        self.target = [w.copy() for w in self.online]
        self.memory = deque(maxlen=50000)
        self.updates = 0
        # A fresh untrained agent defaults to Full49. Loading weights always requires provenance.
        if input_spec is not None and not isinstance(input_spec, InputSpec):
            raise InputContractError('input_spec must be an InputSpec')
        self._input_spec = InputSpec() if input_spec is None else InputSpec.from_dict(input_spec.to_dict())
        self.model_contract_sha256 = None

    @property
    def input_spec(self):
        return self._input_spec

    def prepare_state(self, raw_state):
        return prepare_state(raw_state, self.input_spec)

    def _predict_prepared(self, prepared):
        q = self._forward(prepared.normalized.reshape(1, -1), self.online)[2][0]
        return q, greedy_action(q, prepared.available_actions)

    def predict_greedy(self, raw_state):
        prepared = self.prepare_state(raw_state)
        q, action = self._predict_prepared(prepared)
        return prepared, q, action

    def _init_weights(self, n, h, a):
        # 49→64→64→3，ReLU 的 He 初始化
        rng = self.rng
        return [rng.normal(0, np.sqrt(2/n), (n,h)), np.zeros(h),
                rng.normal(0, np.sqrt(2/h), (h,h)), np.zeros(h),
                rng.normal(0, np.sqrt(2/h), (h,a)), np.zeros(a)]

    @staticmethod
    def _forward(x, weights):
        w1,b1,w2,b2,w3,b3 = weights
        h1 = np.maximum(x@w1+b1, 0)
        h2 = np.maximum(h1@w2+b2, 0)
        q = h2@w3+b3
        return h1,h2,q

    def act(self, raw_state, epsilon=0.0):
        # 先過合法性檢查和正規化；只從可用節點探索或取最大 Q 值
        prepared = self.prepare_state(raw_state)
        choices = prepared.available_actions
        if epsilon > 0 and self.rng.random() < epsilon:
            return int(self.rng.choice(choices))
        return self._predict_prepared(prepared)[1]

    def remember(self, raw_state, action, reward, raw_next_state, done=False):
        # 僅加入已知道 Reward 的轉移；下一狀態也必須來自真實 SimPy
        current = self.prepare_state(raw_state)
        following = self.prepare_state(raw_next_state)
        allowed = current.available_actions
        if int(action) not in allowed:
            raise ValueError('action 指向不可用的節點')
        s = current.normalized
        ns = following.normalized
        mask = np.array([float(i in following.available_actions) for i in range(3)])
        self.memory.append((s,int(action),float(reward),ns,bool(done),mask))

    def _next_q(self, next_states, masks):
        # DQN：目標網路同時負責 argmax 和估值
        values = self._forward(next_states, self.target)[2]
        return np.max(np.where(masks > 0, values, -1e30), axis=1)

    def train_step(self):
        # 回放樣本不足時不更新
        if len(self.memory) < self.batch_size:
            return None
        indexes = self.rng.choice(len(self.memory), self.batch_size, replace=False)
        batch = [self.memory[int(i)] for i in indexes]
        s=np.stack([b[0] for b in batch]); a=np.array([b[1] for b in batch])
        r=np.array([b[2] for b in batch]); ns=np.stack([b[3] for b in batch])
        done=np.array([b[4] for b in batch], dtype=np.float64)
        masks=np.stack([b[5] for b in batch])
        target=r+self.gamma*(1-done)*self._next_q(ns,masks)
        h1,h2,q=self._forward(s,self.online)
        error=np.clip(q[np.arange(len(a)),a]-target,-100,100)
        dq=np.zeros_like(q)
        dq[np.arange(len(a)),a]=2*error/len(a)
        w1,b1,w2,b2,w3,b3=self.online
        grads=[None]*6
        grads[4]=h2.T@dq; grads[5]=dq.sum(axis=0)
        dh2=(dq@w3.T)*(h2>0)
        grads[2]=h1.T@dh2; grads[3]=dh2.sum(axis=0)
        dh1=(dh2@w2.T)*(h1>0)
        grads[0]=s.T@dh1; grads[1]=dh1.sum(axis=0)
        for weight,grad in zip(self.online,grads):
            # 單一張量梯度裁切，避免大 Reward 產生數值爆炸
            norm=np.linalg.norm(grad)
            if norm>5:
                grad=grad*(5/norm)
            weight-=self.lr*grad
        self.updates+=1
        if self.updates % self.target_interval == 0:
            self.target=[w.copy() for w in self.online]
        return float(np.mean(error*error))

    def save(self,path):
        # 權重和介面版本一起存，防止載入7維舊權重
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        payload={f'w{i}':w for i,w in enumerate(self.online)}
        payload['contract']=np.array(CONTRACT_VERSION)
        np.savez(path,**payload)

    def load(self,path, *, contract_ref=None, contract_index=None, expected_sha256=None):
        from .input_contract import file_sha256
        expected = expected_sha256 or file_sha256(path)
        if contract_ref is not None and contract_index is not None:
            raise InputContractError('Supply one contract reference, not two')
        if contract_ref is None:
            contract_ref = contract_from_index(contract_index, self.algorithm, expected)
        spec, _ = validate_model_contract(contract_ref, self.algorithm, path, expected)
        with np.load(path,allow_pickle=False) as file:
            if set(file.files) != {'contract', *(f'w{i}' for i in range(6))}:
                raise InputContractError('Unexpected checkpoint fields')
            if str(file['contract'].item()) != CONTRACT_VERSION:
                raise InputContractError('Checkpoint normalizer version mismatch')
            weights=[file[f'w{i}'].copy() for i in range(6)]
        if any(a.shape != shape or a.dtype.kind != 'f' or not np.isfinite(a).all()
               for a, shape in zip(weights, WEIGHT_SHAPES)):
            raise InputContractError('Invalid weight shapes, dtype or finite values')
        if any(a.shape!=b.shape for a,b in zip(weights,self.online)):
            raise ValueError('模型結構不相符：49維新權重與舊7維權重不可混用')
        self.online=weights
        self.target=[w.copy() for w in weights]
        self._input_spec = spec
        self.model_contract_sha256 = contract_ref.sha256
