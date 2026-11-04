@echo off
setlocal
cd /d "%~dp0"
echo [1/4] Check Docker Compose config...
docker compose config --quiet || exit /b 1
echo [2/4] Container status...
docker compose ps || exit /b 1
echo [3/4] Unit tests (real SimPy installed in backend container)...
docker compose exec -T backend python -m unittest discover -s tests -v || exit /b 1
echo [4/4] Simulation HTTP status and API experiment...
curl.exe -fsS http://localhost:8080/api/offloading/status || exit /b 1
echo.
curl.exe -fsS -X POST http://localhost:8080/api/offloading/experiments -H "Content-Type: application/json" --data "{\"strategies\":[\"local_only\",\"edge_only\",\"cloud_only\",\"load_threshold\",\"latency_aware\"],\"count\":3,\"seed\":42}" > nul || exit /b 1
echo.
echo PASS: 5 policies respond through frontend port 8080.
endlocal
