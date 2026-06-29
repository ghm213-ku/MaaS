import pytest
from pathlib import Path
from app.utils.ssl_utils import generate_self_signed_cert

def test_generate_self_signed_cert(tmp_path):
    cert_file = tmp_path / "cert.pem"
    key_file = tmp_path / "key.pem"
    
    # Generate new cert
    res_cert, res_key = generate_self_signed_cert(cert_file, key_file)
    assert res_cert == cert_file
    assert res_key == key_file
    assert cert_file.exists()
    assert key_file.exists()
    
    # Call again to test existing cert branch
    res_cert2, res_key2 = generate_self_signed_cert(cert_file, key_file)
    assert res_cert2 == cert_file
    assert res_key2 == key_file
