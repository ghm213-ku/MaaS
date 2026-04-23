@echo off
REM Quick startup script for MaaS on Windows

echo.
echo ==================== MaaS Startup ====================
echo Measurement as a Service (HTTPS)
echo ====================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.8+ and add it to your PATH
    pause
    exit /b 1
)

REM Check if main.py exists
if not exist main.py (
    echo ERROR: main.py not found
    echo Please run this script from the MaaS root directory
    pause
    exit /b 1
)

echo Dependencies: Installing...
python -m pip install -q -r requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo Dependencies: OK

echo.
echo Starting MaaS service...
echo.
echo Service will be available at:
echo   - HTTPS API: https://localhost:8443
echo   - Documentation: https://localhost:8443/docs
echo   - Health Check: https://localhost:8443/health
echo.
echo Press Ctrl+C to stop the service
echo.

python main.py

pause
