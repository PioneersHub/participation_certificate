#!/usr/bin/env python
"""Debug why text is not visible"""

from participation_certificate import conf
from participation_certificate.generate_certificates import Certificates
from participation_certificate.preprocess_attendees import Attendee

# Create test attendee
attendee = Attendee(
    full_name="Debug Text",
    first_name="Debug",
    email="debug@example.com",
    ticket_reference="DEBUG-001",
    attended_how="online",
    hash="DEBUG123",
    uuid="debug-text",
)

# First, generate WITHOUT background to see if text appears
print("1. Testing WITHOUT background...")
conf.layout.pdf_background.enabled = False

certs = Certificates([attendee], "test_no_bg")
certs.generate_certificate(attendee)

print("Check _certificates/test_no_bg/debug-text/debug-text.pdf")
print("Does the validation link text appear at the bottom?\n")

# Now with background
print("2. Testing WITH background...")
conf.layout.pdf_background.enabled = True

certs2 = Certificates([attendee], "test_with_bg")
certs2.generate_certificate(attendee)

print("Check _certificates/test_with_bg/debug-text/debug-text.pdf")
print("Does the validation link text appear?")
