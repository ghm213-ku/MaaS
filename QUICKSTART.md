# MaaS Quick Reference

## Starting the Service

### Windows
```bash
run.bat
```

### Linux/macOS
```bash
chmod +x run.sh
./run.sh
```

### Manual Start
```bash
python main.py
```

## Common cURL Commands

### Health Check
```bash
curl -k https://localhost:8443/health
```

### Start Measurement
```bash
curl -k -X POST https://localhost:8443/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "count_rate",
    "duration_seconds": 60,
    "metadata": {"detector": "det_001"}
  }'
```

### Get Status
```bash
curl -k https://localhost:8443/api/v1/measurements/{measurement_id}/status
```

### Stop Measurement
```bash
curl -k -X DELETE https://localhost:8443/api/v1/measurements/{measurement_id}
```

## Using Python Client

```bash
python examples/client_example.py
```

For concurrent measurements:
```bash
python examples/client_example.py concurrent
```

## Environment Variables

```bash
SERVICE_HOST=0.0.0.0
SERVICE_PORT=8443
LOG_LEVEL=INFO
```

## API Documentation

Once running, visit: `https://localhost:8443/docs`

This provides an interactive Swagger UI for testing all endpoints.

## File Structure

```
MaaS/
├── main.py                      # Entry point
├── config.py                    # Configuration
├── requirements.txt             # Dependencies
├── README.md                    # Full documentation
├── QUICKSTART.md               # This file
├── run.bat                      # Windows startup script
├── run.sh                       # Unix startup script
├── certs/                       # Generated SSL certificates
├── app/
│   ├── models.py               # API models
│   ├── api/routes.py           # REST endpoints
│   ├── services/
│   │   ├── measurement.py      # Core service
│   │   └── count_rate.py       # Count-rate handler
│   └── utils/
│       ├── logger.py           # Logging
│       └── ssl_utils.py        # SSL/TLS
└── examples/
    └── client_example.py       # Example usage
```

## Key Features

✓ HTTPS with auto-generated certificates
✓ Async/concurrent measurement support
✓ Unique measurement IDs for tracking
✓ Auto-stop capability
✓ Detailed logging for debugging
✓ Extensible handler architecture
✓ Type-safe Pydantic models
✓ Interactive API documentation (Swagger)

## Adding Custom Measurements

1. Create handler in `app/services/your_handler.py`
2. Register in `main.py` lifespan function
3. Add endpoint in `app/api/routes.py` (optional)
4. Add models in `app/models.py` (optional)

See README.md for detailed examples.

## Debugging

### View detailed logs
```bash
LOG_LEVEL=DEBUG python main.py
```

### Check active measurements
Look for `[measurement_id]` in logs to trace specific measurements.

### SSL Certificate Issues
- Certificates auto-generate on first run in `certs/` folder
- Use `-k` flag in curl to ignore self-signed certificate warnings
- Use `verify=False` in Python requests library
