# Local–Edge–Cloud architecture audit

## Baseline at f8ec356

`workload.load_profile` validates successful buffalo_l CSV rows with >=3 measurements. `profiles.measure_row` measures read, decode, warmup and median detection+recognition separately. `generate_tasks` samples without replacement; `experiment.experiment` creates one manifest and a fresh Simulator per strategy. No actual remote image inference occurs.

`Simulator._process`: arrival -> shared capacity-one decision Resource -> synchronous policy call measured with perf_counter -> optional virtual decision timeout -> outbound RTT/2 -> serialized upload -> capacity-one FCFS CPU -> return RTT/2 -> serialized download -> result. A synchronous model call pauses wall-clock execution of the event loop, but advances virtual time only through the explicit timeout; queued arrivals still execute at their scheduled virtual times.

`_Node` has one CPU and two `_SerializedLink` Resources. Edge and Cloud links are independent (model A), and uplink/downlink are independent full duplex. Each transfer monopolizes its link, not processor sharing. RTT consumes time but not channel capacity. Local bypasses all network stages. MB/KB are decimal; upload milliseconds = MB*8000/Mbps, result = KB*8/Mbps. Result size defaults to 16 KB. Speeds default to 1/3/8, RTT 0/20/100 ms, bandwidth 1000/120/55 Mbps (`DEFAULT_NODES`, `NodeConfig`). CPU capacity is deliberately one per node.

`Task` includes actual inference and face count; `estimate_latency` and `LayaStrategy.select_node` consume these. This is oracle information, despite the original observable-contract docstring. `Node.state` derives true outstanding CPU work from a future work_until and omits tasks still transmitting. `queue_samples` samples only at decisions. `metrics` assumes completion=1/drop=0. DQN/DDQN are rejected; no training interface existed.

## Confirmed findings and planned corrections

|Priority|Evidence|Correction|
|---|---|---|
|P0|strategies.estimate_latency, laya_client.select_node consume actual per-image labels|Separate DecisionTask, historical disjoint calibration, explicit realistic/oracle|
|P0|_process increments outstanding only after upload|Track commitments, transmission, CPU waiting/running and returning independently with estimated work|
|P0|_process reports decision_ms although ablation advances no time|Report wall measurement separately; charged component zero in ablation|
|P1|Node.state uses actual future remaining service|Estimate remaining work from historical estimate and elapsed observable service, never true scheduled finish|
|P1|Only decision-sampled queue means|Integrate CPU waiting count over virtual time|
|P1|Independent channels could be mistaken for shared access|Explicit independent/shared modes and hand-calculated contention tests|
|P1|metrics hardcodes completion|Explicit complete_all and stage-boundary drop_if_expired; account for consumed stages|
|P1|No RL transitions/reset|Shared DecisionTask/State/Action transition adapter, no trained-policy claim|

Original evidence remains under `work/audit/before`. Final validation and model limitations will be appended after tests.
