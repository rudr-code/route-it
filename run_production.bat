@echo off
echo ========================================================
echo Starting Route.it - Quantum Fleet Logistics Platform
echo Production Unified Mode (Port 8001)
echo ========================================================

cd /d "%~dp0"
echo 1. Checking frontend build in dashboard/dist...
if not exist "dashboard\dist\index.html" (
    echo Building dashboard frontend...
    cd dashboard
    call npm install
    call npm run build
    cd ..
)

echo 2. Launching unified FastAPI server on http://localhost:8001 ...
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
pause
