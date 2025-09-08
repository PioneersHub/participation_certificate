#!/usr/bin/env python
"""Test with a real-looking attendee to verify name visibility"""

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

# Test with a realistic name
attendee = Attendee(
    full_name="Alexander CS Hendorf",
    first_name="Alexander",
    email="alex@pycon.de",
    ticket_reference="PYCON-2025-001",
    attended_how="on site",
    hash="ALEX2025",
    uuid="test-real-name",
)

print("🎯 Testing with realistic attendee data...")
print(f"Name: {attendee.full_name}")
print(f"Hash: {attendee.hash}")
print()

# Enable PDF background
conf.layout.pdf_background.enabled = True

certs = Certificates([attendee], "real_attendee_test")
certs.generate_certificate(attendee)

pdf_path = (
    conf.dirs.path_to_certificates / "real_attendee_test" / attendee.uuid / f"{attendee.uuid}.pdf"
)
if pdf_path.exists():
    print(f"✅ Certificate generated: {pdf_path}")
    import subprocess

    subprocess.run(["open", str(pdf_path)], check=False)
    print("\n🔍 Check that:")
    print("   • The name 'Alexander CS Hendorf' is visible")
    print("   • The hash 'No. ALEX2025' is visible")
    print("   • The blue validation link is visible at the bottom")
    print("   • All text appears correctly on the PDF background")
else:
    print("❌ Failed to generate certificate")
