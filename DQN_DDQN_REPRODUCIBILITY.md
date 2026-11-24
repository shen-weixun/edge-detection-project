# 49 維模型與實驗重現

新的 `study.json` 是版本帳目，`selected-checkpoints.json` 是唯一正式選模記錄。上一輪 ZIP 不變。原始執行 runner 與 source-snapshot 中的修正 runner 各有 SHA，從對應 ZIP 成員及重現結果交叉驗證。獨立修正驗證的 `agents49_revalidate.py` 亦有 SHA，並列出各候選使用的驗證 profile、來源圖片、到達間隔及逐次摘要的雜湊。

|模型 seed 42|原 Validation reward|修正後 Validation reward|Checkpoint SHA-256|
|---|---:|---:|---|
|DQN|-1.338019|-1.378032|`4ca02e6543ac8bdb5dd25e608eda15ddd5a5726e7f3b716051748143dc4f118c`|
|DDQN|-1.256887|-1.287144|`4bc95eeaf87f8278541b99c95846275611473159fc7f746d5ebe49ca7242b91e`|

三個訓練種子為 42／43／44。驗證種子 101／103，每次 10 張驗證圖，24 個情境、1,000 ms Deadline、停用虛擬決策成本。驗證到達間隔為訓練參考工作量均值除以 Edge 速度 3 和目標 rho。相同 Docker 環境重訓比對六組權重、逐步轉移與 288 組驗證輸入及摘要。摘要的 wall-clock 診斷值隨執行變動，排除該欄做精確比較。正式擴充使用 211／307／401 固定種子，啟動前封存 workload 順序、時程、估計器、設定和 checkpoint，且以 `design.json` SHA 綁定結果。

以下從專案根目錄重現，沿用原 ZIP 的 `frozen-profiles` 及成員模型 ZIP。先在獨立輸出目錄重跑 provenance，再讓 Compose 的 backend 以相同依賴執行。將 `scripts/agents49*.py` 複製到容器 `/app/scripts`，組員原始 ZIP 的解壓根目錄複製到 `/tmp/agents49-member/source`。將下列 `agents49-final` 換成新輸出名稱。命令失敗時停止後續階段。

```powershell
python scripts/agents49_finalize_provenance.py . PATH_TO_PREVIOUS_ZIP profiles/agents49-final
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python /app/scripts/agents49_experiment.py train --output /profiles/agents49-final/reproduction --member /tmp/agents49-member/source --archive /profiles/ai-comparison
docker compose exec -T backend python /app/scripts/agents49_final_gate.py /profiles/agents49 /profiles/agents49-final /profiles
foreach ($stage in 'freeze','expanded','laya-subset') {
    docker compose exec -T -e OPENBLAS_NUM_THREADS=1 -e OMP_NUM_THREADS=1 backend python /app/scripts/agents49_expand.py $stage --old /profiles/agents49 --out /profiles/agents49-final --member /tmp/agents49-member/source --archive /profiles/ai-comparison
    if ($LASTEXITCODE -ne 0) { break }
}
foreach ($stage in 'expanded','laya-subset') {
    docker compose exec -T -e OPENBLAS_NUM_THREADS=1 backend python /app/scripts/agents49_final_report.py $stage /profiles/agents49-final /profiles
    if ($LASTEXITCODE -ne 0) { break }
}
```

本輪報表稽核第一次因 phase 聚合誤讀欄名而中止。修正報表後重跑，原始資料與設計 hash 維持相同，保留第一次錯誤日誌。推論 wall-clock 會因平台、資源負荷和服務成本而變，正式效能比較不要求位元一致。

