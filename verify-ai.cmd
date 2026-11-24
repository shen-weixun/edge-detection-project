@echo off
setlocal
cd /d "%~dp0"
echo [1/3] Laya service containers...
docker compose -f compose.yaml -f compose.ai.yaml ps || exit /b 1
echo [2/3] Laya package import inside dedicated container...
docker compose -f compose.yaml -f compose.ai.yaml exec -T laya python -c "from laya import Router; print('Laya package import OK')" || exit /b 1
echo [3/3] Actual Laya inference (first run downloads model)...
curl.exe -fsS -X POST http://localhost:8080/api/offloading/experiments -H "Content-Type: application/json" --data "{\"strategies\":[\"laya\"],\"count\":1,\"seed\":42}" || exit /b 1
echo.
echo PASS: actual Laya decision returned a simulation result.
endlocal
