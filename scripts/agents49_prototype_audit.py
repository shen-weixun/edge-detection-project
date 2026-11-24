"""Compare original prototype artifacts and reproduce its pre-completion leak."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import numpy as np


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("member", "reproduction", "zip", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.member.resolve()))
    from app.offloading.rl.event_environment import EventEnvironment, Task
    from app.offloading.rl.normalizer import FEATURE_NAMES

    leak = []
    for actual in (100, 300):
        env = EventEnvironment(seed=42, scenario="network")
        env.dispatch(Task(0, 0, .2, 640, 480, 1000, 150, actual), 0)
        env.now = 10
        probe = Task(1, 10, .2, 640, 480, 1000, 150, 150)
        obs = dict(zip(FEATURE_NAMES, env.observation(probe).tolist()))
        assert not env.pop_completed()
        leak.append({"hidden_actual_ms": actual, "completed": 0, "observed_at_ms": 10,
                     "local_queue_work_ms": obs["local.queue_work_ms"],
                     "local_download_backlog_ms": obs["local.download_backlog_ms"]})
    assert [case["local_queue_work_ms"] for case in leak] == [90, 290]

    checksums = {}
    for line in (args.member / "SHA256_MANIFEST.txt").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        assert digest(args.member / name) == expected, name
        checksums[name] = expected

    models = {}
    for name in ("dqn", "ddqn"):
        original = args.member / "models" / f"{name}_49d.npz"
        reproduced = args.reproduction / "models" / original.name
        original_log = args.member / "logs" / f"{name}_completed.csv"
        reproduced_log = args.reproduction / "logs" / original_log.name
        assert original_log.read_bytes().splitlines() == reproduced_log.read_bytes().splitlines()
        meta = json.loads((args.reproduction / "logs" / f"{name}_metadata.json").read_text(encoding="utf-8"))
        with np.load(original, allow_pickle=False) as a, np.load(reproduced, allow_pickle=False) as b:
            tensor_diffs = {f"w{i}": float(np.max(np.abs(a[f"w{i}"] - b[f"w{i}"]))) for i in range(6)}
        models[name] = {"original_sha256": digest(original), "reproduced_sha256": digest(reproduced),
                        "max_abs_tensor_differences": tensor_diffs, "completion_csv_rows_equal": True,
                        "metadata": meta}
    args.output.write_text(json.dumps({"zip_sha256": digest(args.zip), "member_checksums": checksums,
                                       "numpy": np.__version__, "leak_reproduction": leak,
                                       "reproduction": models}, indent=2), encoding="utf-8")

