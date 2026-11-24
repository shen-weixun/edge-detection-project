# Reproduction and scope

The original run used existing image sha256:5f866c46ea75f21e9fa98ae0c516f6cd2f7dc4d8bed578db74e1c38048e16530, --network none --read-only --tmpfs /tmp, OPENBLAS_NUM_THREADS=1 and OMP_NUM_THREADS=1. Only the new candidate directory was mounted at /delivery. SQLite memory was used; no DB/API/dataset image/model cache mount.

prepare_candidate.py verified the accepted Smoke ZIP/input SHA and all330 original protected files, then sealed candidate-input.zip.
Execution command: docker run --rm --network none --read-only --tmpfs /tmp --mount "type=bind,source=<NEW_AUTHORIZED_CANDIDATE_DIRECTORY>,target=/delivery" -w /tmp -e PYTHONDONTWRITEBYTECODE=1 -e OPENBLAS_NUM_THREADS=1 sha256:5f866c46ea75f21e9fa98ae0c516f6cd2f7dc4d8bed578db74e1c38048e16530 python -B /delivery/run_candidate_container.py

Execution is single-use and protected by EXECUTION_RESERVED.json. Do not remove it or rerun this completed authorization. Repeating training requires new authorization and a new directory containing the sealed inputs and unchanged harness.

The data/profile CSVs are Training and Validation only. Every model was initialized anew; Smoke weights were not resumed. Initial/2400/4800/7200/9600 snapshots are preserved. The final9600 snapshot was evaluated for EVERY seed; no best-model choice.

Inside the evidence root, candidate-results/models contains checkpoints and source-bound input-contract-index.json; runtime/,tools/,candidate_tools/,data/,results/design preserve their relative source paths. training-state.npz plus checkpoint.json retain online,target,Replay,RNG/counters for audit; no resume command was executed.

Full raw results are lossless .json.gz, update traces are .jsonl.gz. candidate-results/reports provides unranked stratified CSVs and figures. RUN_SHA256.json verifies the isolated run payload; DELIVERY_SHA256.json verifies this final package.

Midpoint monitor summaries across24 heterogeneous cases are learning diagnostics, not a pooled strategy ranking. Unseen E RTT310 is a small extrapolation beyond Training max300; do not call every unseen case interpolation. Historical hardware/thread provenance and16KB result assumptions remain limitations.
