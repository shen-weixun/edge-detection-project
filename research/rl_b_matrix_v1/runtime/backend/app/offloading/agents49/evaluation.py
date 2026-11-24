"""Independent frozen evaluation state, including a separate random generator."""
from copy import deepcopy
import numpy as np


def evaluation_snapshot(agent, seed):
    frozen = deepcopy(agent)
    frozen.rng = np.random.default_rng(seed)
    if hasattr(frozen, "traces"):
        frozen.traces = []
    return frozen

