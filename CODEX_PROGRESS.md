# SimPy audit progress

- Baseline commit: `f8ec3563aada7f574f9264da95314b9a599ee4ef`; initial working tree clean.
- Read models, simulator, strategies, experiment, workload, clients, API, profiler, Laya service, tests, scripts, Compose and simulator UI.
- Existing nine-run evidence copied without modification into `work/audit/before/`.
- Confirmed P0: true work and face count exposed to policies; invisible work committed in upload; ablation component inconsistency.
- Implementation and regression tests in progress. Docker Desktop was stopped; starting it for baseline/build/integration.
- Do not delete volumes or datasets. Continue with `docker compose -f compose.yaml -f compose.ai.yaml up -d --build`, then unit and integration checks.

- Core implementation now separates DecisionTask, historical calibration, commitments/CPU/return phases, independent/shared serialized links, stage-boundary expiration and wall/charged decision time. RL event-stepped adapter added.
- Baseline container: 28/28 tests passed. New suite reached 49 cases; corrected a hand-case deadline (171.6 ms completion must be tested against 171, not 175). Full precision results retained; old exact 600-ms assertion now uses 1e-8 floating tolerance.
- First calibration seed 20261104 overlapped one test image and is excluded. Verified seed=100 against DB identities before starting independent calibration a057ded0f08c4837beff2ffd02f390ee. Original 30-image test Profile remains 6ddb0a187ba44065a5beaf0450ad259e.
