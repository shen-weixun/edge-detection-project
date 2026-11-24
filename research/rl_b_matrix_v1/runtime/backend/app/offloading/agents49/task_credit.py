"""Task-terminal delayed feedback on the native SimPy environment.

Contextual cost regression, gamma=0. No next-decision bootstrap.
"""
from ..integration_contract import feature_vector
from ..rl import OffloadingEnv


def train_task_episode(agent, tasks, *, epsilon_for_step, config):
    if agent.gamma != 0:
        raise ValueError("Task-terminal objective requires gamma=0")
    env = OffloadingEnv(tasks, **config)
    observation = env.reset()
    pending = {}
    records = []
    dispatches = 0
    while observation is not None:
        task, state = observation
        features = feature_vector(task, state)
        if task.task_id in pending:
            raise ValueError("Duplicate dispatch")
        action = agent.act(features, epsilon=epsilon_for_step(dispatches))
        pending[task.task_id] = (features, action, dispatches)
        dispatches += 1
        observation, _, episode_done, info = env.step(action)
        for terminal in info["terminal_rewards"]:
            tid = terminal["task_id"]
            if tid not in pending:
                raise ValueError("Unknown or duplicate completion")
            original, original_action, ordinal = pending.pop(tid)
            # Terminal bootstrap is masked. The API still validates this vector.
            # It is a storage placeholder, not a next-state observation.
            agent.remember(original, original_action, terminal["reward"], original, True)
            loss = agent.train_step()
            records.append(dict(task_id=tid, action=original_action, dispatch_index=ordinal,
                                feedback_at_ms=info["time_ms"], reward=terminal["reward"],
                                task_done=True, episode_done=episode_done, loss=loss))
    if pending or len(records) != len(tasks):
        raise ValueError("Unsettled episode")
    return records

