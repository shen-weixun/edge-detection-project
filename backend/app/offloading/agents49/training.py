"""Train on native OffloadingEnv transitions and reconcile task completions."""
import math

from ..integration_contract import feature_vector
from ..rl import OffloadingEnv

# remember() validates availability even for terminal next states. The terminal
# mask disables bootstrapping. The last observation is used as a placeholder.
def train_episode(agent, tasks, *, epsilon_for_step, config):
    env = OffloadingEnv(tasks, **config)
    observation = env.reset()
    if observation is None:
        raise ValueError("Training episode must include an actionable task")
    dispatched = set()
    completed = {}
    transitions = []
    while observation is not None:
        task, state = observation
        if task.task_id in dispatched:
            raise ValueError("Duplicate decision")
        dispatched.add(task.task_id)
        features = feature_vector(task, state)
        epsilon = epsilon_for_step(len(transitions))
        action = agent.act(features, epsilon=epsilon)
        next_observation, reward, done, info = env.step(action)
        terminals = info["terminal_rewards"]
        for item in terminals:
            task_id = item["task_id"]
            if task_id not in dispatched or task_id in completed:
                raise ValueError("Completion does not match a dispatched task exactly once")
            completed[task_id] = item
        if not math.isclose(reward, sum(item["reward"] for item in terminals)):
            raise ValueError("Invalid step reward")
        if done != (next_observation is None):
            raise ValueError("Inconsistent terminal transition")
        next_features = features if done else feature_vector(*next_observation)
        agent.remember(features, action, reward, next_features, done)
        loss = agent.train_step()
        if loss is not None and not math.isfinite(loss):
            raise ValueError("Nonfinite training loss")
        transitions.append({
            "task_id": task.task_id, "action": action, "epsilon": epsilon,
            "reward": reward, "done": done, "loss": loss, "time_ms": info["time_ms"],
            "next_task_id": None if done else next_observation[0].task_id,
            "terminal_rewards": terminals,
        })
        observation = next_observation
    if dispatched != completed.keys() or len(completed) != len(tasks):
        raise ValueError("Episode ended before all tasks settled")
    return transitions

