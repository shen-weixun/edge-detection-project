# B matrix v1: standalone research tools and immutable runtime snapshot

This directory does not replace backend/ and does not register candidates in API.
runtime/ preserves the original tested source paths. data/ contains only small
Training/Validation measurement CSV/JSON and the split manifest, not face photos.
The split manifest can mention frozen Test identities; no Test profile timing CSV
is included or consumed. Full task manifests, model contracts/weights, Replay,
TD and per-task outputs are in the Release evidence assets.

All experiment outcomes, including failures, are in ../../docs/rl_b_matrix_v1/.
Review B_CANDIDATE_REVIEW_ZH_TW.md before using any model. These are candidates,
not Test-accepted deployment models.

Exact reproduction requires sealed accepted-smoke-input.zip,
candidate-input.zip and historical-p0-kit.zip from the evidence archive's
reproduction/ directory. Put them with run_candidate_container.py in a NEW
execution directory after a NEW training authorization. Do not rerun the
completed budget or remove its EXECUTION_RESERVED.json guard.

The current repository CI only installs SimPy and runs test_offloading.py.
A green current CI is not proof that the complete130 tests were run on GitHub.
The runtime tests snapshot is for the explicit research entry point, not a second
production backend. No training or deployment is triggered by copying this folder.
