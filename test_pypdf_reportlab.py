#!/usr/bin/env python
"""Test pypdf with reportlab overlay - the most reliable approach"""

import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from participation_certificate import conf
from participation_certificate.preprocess_attendees import Attendee

# Test attendee
attendee = Attendee(
    full_name="Alexander CS Hendorf",
    first_name="Alexander",
    email="test@example.com",
    ticket_reference="TEST-001",
    attended_how="on site",
    hash="ALEX2025",
    uuid="pypdf-test",
)

# Get background PDF
bg_file = Path(conf.dirs.graphics) / conf.layout.pdf_background.file
output_file = Path("test_pypdf_reportlab.pdf")

print("Testing pypdf/reportlab approach (most reliable)...")
print(f"Background: {bg_file}")
print(f"Attendee: {attendee.full_name}")

# Step 1: Read the existing background PDF
reader = PdfReader(str(bg_file))
background_page = reader.pages[0]

# Get page dimensions
page_width = float(background_page.mediabox.width)
page_height = float(background_page.mediabox.height)
print(f"Page dimensions: {page_width} x {page_height}")

# Step 2: Create overlay with text using reportlab
packet = io.BytesIO()
can = canvas.Canvas(packet, pagesize=(page_width, page_height))

# Add fonts and text - positions from config
# Note: reportlab uses bottom-left origin, config uses top-left
# So we need to convert y coordinates: y_reportlab = page_height - y_config

# Attendee name (from config: x=50, y=180)
can.setFont("Helvetica-Bold", 24)
y_pos = page_height - 180
can.drawString(50, y_pos, attendee.full_name)

# Hash (from config: x=532, y=128)
y_pos = page_height - 128
can.drawString(532, y_pos, f"No. {attendee.hash}")

# Multi-line text (from config: x=45, y=200)
can.setFont("Helvetica", 16)
y_pos = page_height - 200
text_lines = ["has attended the PyCon DE & PyData 2025", f"conference {attendee.attended_how}."]
for i, line in enumerate(text_lines):
    can.drawString(45, y_pos - (i * 20), line)

# Footer link (from config: x=45, y=-33 which means from bottom)
can.setFont("Helvetica", 8)
can.setFillColorRGB(77 / 255, 170 / 255, 220 / 255)  # Blue color
y_pos = 33  # From bottom
link_text = "Validate this certificate online"
link_url = f"https://certificates.euroscipy.org/{attendee.uuid}/"
can.drawString(45, y_pos, link_text)
# Add actual link annotation
can.linkURL(link_url, (45, y_pos - 5, 200, y_pos + 10), relative=0)

# Save the overlay
can.save()

# Step 3: Merge overlay with background
packet.seek(0)
overlay_reader = PdfReader(packet)
overlay_page = overlay_reader.pages[0]

# Merge pages - overlay on top of background
background_page.merge_page(overlay_page)

# Step 4: Write the result
writer = PdfWriter()
writer.add_page(background_page)

# Add metadata
writer.add_metadata(
    {
        "/Title": f"Certificate for {attendee.full_name}",
        "/Author": "Python Softwareverband e.V.",
        "/Subject": "PyCon DE & PyData 2025 Certificate of Attendance",
        "/Keywords": "PyCon, PyData, Certificate",
        "/Creator": "participation_certificate with pypdf/reportlab",
    }
)

# Set encryption (no editing allowed)
writer.encrypt(
    user_password="",  # No user password
    owner_password="admin123",  # Owner password for restrictions
    permissions_flag=(1 << 2) | (1 << 11),  # Allow printing only
)

# Save output
with open(output_file, "wb") as output:
    writer.write(output)

print(f"✅ Created {output_file}")
print("The background PDF should be fully visible with text on top!")

import subprocess

subprocess.run(["open", str(output_file)], check=False)
