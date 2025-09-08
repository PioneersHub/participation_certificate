#!/usr/bin/env python
"""Final test with both visible text and clickable link"""

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

attendee = Attendee(
    full_name="Final Complete Test",
    first_name="Final",
    email="final@example.com",
    ticket_reference="FINAL-001",
    attended_how="on site",
    hash="FINAL999",
    uuid="final-complete",
)

print("🎉 FINAL TEST - Certificate with PDF background")
print("Expected: Blue text 'Validate this certificate online' with link to:")
print(f"          https://certificates.euroscipy.org/{attendee.uuid}/")
print()

certs = Certificates([attendee], "final_complete")
certs.generate_certificate(attendee)

pdf_path = (
    conf.dirs.path_to_certificates / "final_complete" / attendee.uuid / f"{attendee.uuid}.pdf"
)
if pdf_path.exists():
    print(f"✅ Certificate generated: {pdf_path}")
    import subprocess

    subprocess.run(["open", str(pdf_path)], check=False)
    print("\n✨ The certificate should now have:")
    print("   • Professional PDF background design")
    print("   • Visible blue text at the bottom")
    print("   • Clickable link for validation")
else:
    print("❌ Failed to generate")
