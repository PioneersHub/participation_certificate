#!/usr/bin/env python
"""Create a test self-signed certificate for testing PDF signing"""

import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

# Certificate details
cert_dir = Path("_signatures")
cert_dir.mkdir(exist_ok=True)

# Generate private key
print("🔑 Generating RSA private key...")
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Create certificate
print("📜 Creating self-signed certificate...")
subject = issuer = x509.Name(
    [
        x509.NameAttribute(NameOID.COUNTRY_NAME, "DE"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Berlin"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Berlin"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PyCon DE Test"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Test Certificate"),
    ]
)

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(private_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.utcnow())
    .not_valid_after(
        # Certificate valid for 1 year
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    )
    .add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]),
        critical=False,
    )
    .sign(private_key, hashes.SHA256())
)

# Create PKCS#12 bundle
print("📦 Creating PKCS#12 bundle...")
p12_password = b"test"
p12 = pkcs12.serialize_key_and_certificates(
    name=b"Test Certificate",
    key=private_key,
    cert=cert,
    cas=None,
    encryption_algorithm=serialization.BestAvailableEncryption(p12_password),
)

# Save the certificate
p12_path = cert_dir / "test.p12"
with open(p12_path, "wb") as f:
    f.write(p12)

print(f"✅ Test certificate created: {p12_path}")
print("   Password: test")
print("\nYou can now test PDF signing with this certificate!")
