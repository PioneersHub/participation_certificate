#!/usr/bin/env python
"""Test with fixed position and color"""

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

attendee = Attendee(
    full_name="Fixed Test User",
    first_name="Fixed",
    email="fixed@example.com",
    ticket_reference="FIX-001",
    attended_how="on site",
    hash="FIX123",
    uuid="fixed-test",
)

print("Testing with FIXED configuration:")
print("✓ Position: x=45 (not -45)")
print("✓ Color: dark blue (0, 0, 139)")
print(f"✓ Link URL: https://certificates.euroscipy.org/{attendee.uuid}/")

certs = Certificates([attendee], "fixed_test")
certs.generate_certificate(attendee)

pdf_path = conf.dirs.path_to_certificates / "fixed_test" / attendee.uuid / f"{attendee.uuid}.pdf"
if pdf_path.exists():
    print(f"\n✅ Certificate generated: {pdf_path}")
    import subprocess

    subprocess.run(["open", str(pdf_path)], check=False)
    print("\nCheck that:")
    print("• Text is VISIBLE in dark blue")
    print("• Text is CLICKABLE as a link")
    print("• Link opens the validation URL")
