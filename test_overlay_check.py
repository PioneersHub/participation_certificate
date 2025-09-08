#!/usr/bin/env python
"""Check if text is in overlay"""

from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

attendee = Attendee(
    full_name="Overlay Check",
    first_name="Overlay",
    email="overlay@example.com",
    ticket_reference="OVER-001",
    attended_how="online",
    hash="OVER123",
    uuid="overlay-check",
)

print("Generating certificate to check overlay...")
certs = Certificates([attendee], "overlay_test")
certs.generate_certificate(attendee)

print("\nCheck these files:")
print(
    "1. _certificates/overlay_test/overlay-check/overlay_debug.pdf - The overlay (should have text)"
)
print("2. _certificates/overlay_test/overlay-check/overlay-check.pdf - The merged result")
print("\nDoes the text appear in overlay_debug.pdf?")
