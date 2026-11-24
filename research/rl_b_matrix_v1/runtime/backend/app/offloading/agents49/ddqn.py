"""DDQN：Online 挑動作；Target 評估該動作，其餘介面與 DQN 相同。"""
import numpy as np
from .dqn import DQN


class DDQN(DQN):
    algorithm = 'ddqn'

    def _next_q(self, next_states, masks):
        # 以 Online Q 選下一步動作，再用 Target Q 估值
        online_q = self._forward(next_states, self.online)[2]
        chosen = np.argmax(np.where(masks > 0, online_q, -1e30), axis=1)
        target_q = self._forward(next_states, self.target)[2]
        return target_q[np.arange(len(chosen)), chosen]
