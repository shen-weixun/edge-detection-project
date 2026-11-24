"""Connect a frozen NumPy checkpoint to the native SimPy decision contract."""
from ..integration_contract import ACTIONS, FEATURE_NAMES, IndexPolicy
from . import normalizer
from .input_contract import InputContractError
from .ddqn import DDQN
from .dqn import DQN

AGENTS = {"dqn": DQN, "ddqn": DDQN}
WEIGHT_SHAPES = ((49, 64), (64,), (64, 64), (64,), (64, 3), (3,))


def load_agent(algorithm, checkpoint, expected_sha256, *, contract_ref=None, contract_index=None):
    if FEATURE_NAMES != normalizer.FEATURE_NAMES or ACTIONS != ("local", "edge", "cloud"):
        raise ValueError("Simulator feature or action contract has changed")
    if algorithm not in AGENTS:
        raise InputContractError('Unknown algorithm')
    agent = AGENTS[algorithm]()
    agent.load(checkpoint, expected_sha256=expected_sha256,
               contract_ref=contract_ref, contract_index=contract_index)
    return agent


class Agent49Policy(IndexPolicy):
    """Greedy epsilon=0 decision with one forward pass and an in-memory trace."""

    def __init__(self, agent):
        self.agent = agent
        self.decisions = []
        super().__init__(self.choose)

    def select_node(self, task, state):
        node = super().select_node(task, state)
        self.decisions[-1]["task_id"] = task.task_id
        return node

    def choose(self, features):
        prepared, q_values, action = self.agent.predict_greedy(features)
        self.decisions.append({
            "raw_features": prepared.raw.tolist(), "masked_features": prepared.masked.tolist(),
            "normalized_features": prepared.normalized.tolist(),
            "available_actions": list(prepared.available_actions),
            "input_contract_sha256": self.agent.input_spec.sha256,
            "model_contract_sha256": self.agent.model_contract_sha256,
            "q_values": q_values.tolist(), "action": action, "node": ACTIONS[action],
        })
        return action

