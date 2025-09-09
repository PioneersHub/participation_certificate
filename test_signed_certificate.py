#!/usr/bin/env python
"""Test digital signing with pypdf/reportlab approach"""

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

# Test attendee
attendee = Attendee(
    full_name="Signed Certificate Test",
    first_name="Signed",
    email="signed@example.com",
    ticket_reference="SIGN-001",
    attended_how="on site",
    hash="SIGN2025",
    uuid="signed-test",
)

print("🔐 Testing digital signing with pypdf/reportlab approach...")
print(f"Attendee: {attendee.full_name}")

# Check if we have a test certificate
sign_key_path = conf.dirs.path_to_signatures / "test.p12"
if not sign_key_path.exists():
    print(f"⚠️  No test certificate found at {sign_key_path}")
    print("Creating unsigned certificate...")
    sign_key = None
    sign_password = None
else:
    print(f"✅ Using certificate: {sign_key_path}")
    sign_key = sign_key_path
    sign_password = b"test"  # Replace with actual password

# Enable PDF background
conf.layout.pdf_background.enabled = True

# Create certificates with or without signing
certs = Certificates([attendee], "signed_test", sign_key=sign_key, sign_password=sign_password)

certs.generate_certificate(attendee)

pdf_path = conf.dirs.path_to_certificates / "signed_test" / attendee.uuid / f"{attendee.uuid}.pdf"
if pdf_path.exists():
    print(f"✅ Certificate generated: {pdf_path}")

    # Check if PDF is signed (basic check - look for signature in file)
    with open(pdf_path, "rb") as f:
        pdf_content = f.read()
        if b"/Type /Sig" in pdf_content or b"/ByteRange" in pdf_content:
            print("🔒 PDF appears to be digitally signed!")
        else:
            print("⚠️  PDF does not appear to be signed")

    import subprocess

    subprocess.run(["open", str(pdf_path)], check=False)

    print("\n📋 Check that:")
    print("   • Background PDF is visible")
    print("   • Text appears in white on top")
    print("   • PDF shows signature if certificate was available")
else:
    print("❌ Failed to generate certificate")
