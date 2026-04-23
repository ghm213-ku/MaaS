"""SSL/TLS certificate utilities."""
import os
from pathlib import Path
from datetime import datetime, timedelta
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from .logger import configure_logging

logger = configure_logging(__name__)


def generate_self_signed_cert(
    cert_file: Path,
    key_file: Path,
    days_valid: int = 365,
    hostname: str = "localhost"
) -> tuple[Path, Path]:
    """
    Generate a self-signed SSL/TLS certificate if it doesn't exist.
    
    Args:
        cert_file: Path to certificate file
        key_file: Path to private key file
        days_valid: Number of days the certificate is valid
        hostname: Hostname for the certificate (CN and SAN)
        
    Returns:
        Tuple of (cert_path, key_path)
        
    Raises:
        Exception: If certificate generation fails
    """
    # Check if certificates already exist
    if cert_file.exists() and key_file.exists():
        logger.info(f"Using existing SSL certificate: {cert_file}")
        return cert_file, key_file
    
    logger.info(f"Generating new self-signed SSL certificate for {hostname}")
    logger.debug(f"Certificate will be valid for {days_valid} days")
    
    try:
        # Generate private key
        logger.debug("Generating RSA private key (2048-bit)")
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Build certificate subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Local"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MaaS"),
            x509.NameAttribute(NameOID.COMMON_NAME, hostname),
        ])
        
        # Build certificate
        logger.debug("Building X.509 certificate")
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.utcnow())
            .not_valid_after(datetime.utcnow() + timedelta(days=days_valid))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(hostname),
                    x509.DNSName("*.local"),
                    x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
                ]),
                critical=False,
            )
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )
        
        # Ensure directory exists
        cert_file.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Certificate directory ready: {cert_file.parent}")
        
        # Write certificate to file
        logger.debug(f"Writing certificate to {cert_file}")
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        
        # Write private key to file
        logger.debug(f"Writing private key to {key_file}")
        with open(key_file, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
        
        # Set restrictive permissions on key file (on Unix-like systems)
        if hasattr(os, "chmod"):
            os.chmod(key_file, 0o600)
            logger.debug(f"Set restrictive permissions on private key: {key_file}")
        
        logger.info(f"SSL certificate generated successfully")
        logger.info(f"Certificate: {cert_file}")
        logger.info(f"Private Key: {key_file}")
        
        return cert_file, key_file
        
    except Exception as e:
        logger.error(f"Failed to generate SSL certificate: {e}", exc_info=True)
        raise
