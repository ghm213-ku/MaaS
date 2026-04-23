#!/bin/bash

echo ""
echo "==================== MaaS Startup ===================="
echo "Measurement as a Service (HTTPS)"
echo "===================================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found"
    echo "Please install Python 3.8+ and ensure it's in your PATH"
    exit 1
fi

# Check if main.py exists
if [ ! -f main.py ]; then
    echo "ERROR: main.py not found"
    echo "Please run this script from the MaaS root directory"
    exit 1
fi

echo "Checking Python version..."
python3 --version

echo ""
echo "Dependencies: Installing..."
python3 -m pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
echo "Dependencies: OK"

echo ""
echo "Starting MaaS service..."
echo ""
echo "Service will be available at:"
echo "  - HTTPS API: https://localhost:8443"
echo "  - Documentation: https://localhost:8443/docs"
echo "  - Health Check: https://localhost:8443/health"
echo ""
echo "Press Ctrl+C to stop the service"
echo ""

python3 main.py
