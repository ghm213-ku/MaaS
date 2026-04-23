"""Application configuration."""
import os
from pathlib import Path

# Service Configuration
SERVICE_HOST = os.getenv("SERVICE_HOST", "0.0.0.0")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", 8443))
SERVICE_NAME = "Measurement as a Service (MaaS)"

# SSL/TLS Configuration
CERTS_DIR = Path(__file__).parent / "certs"
SSL_CERT_FILE = CERTS_DIR / "cert.pem"
SSL_KEY_FILE = CERTS_DIR / "key.pem"
SSL_CERT_DAYS = 365

# Logging Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
