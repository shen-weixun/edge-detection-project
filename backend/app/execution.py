from time import perf_counter
from typing import Literal

Strategy = Literal['fixed', 'latency_aware', 'dqn_ddqn', 'decision_model']

def execute_local(fn, strategy: Strategy):
    """All strategies currently share the local baseline, without offloading."""
    started = perf_counter()
    result = fn()
    elapsed_ms = (perf_counter() - started) * 1000
    return {
        **result,
        'strategy': strategy,
        'execution_target': 'device',
        'execution_mode': 'local_baseline',
        'timings_ms': {'device': round(elapsed_ms, 3), 'edge': None, 'cloud': None},
        'timing_scope': 'Local backend processing: image decoding, model initialization if needed, inference and lock wait. Excludes upload/network and database writes.',
    }
