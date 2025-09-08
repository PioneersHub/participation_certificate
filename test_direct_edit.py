#!/usr/bin/env python
"""Test directly editing background PDF with reportlab"""

import io
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from participation_certificate import conf
from participation_certificate.preprocess_attendees import Attendee

# Test attendee
attendee = Attendee(
    full_name="Direct Edit Test",
    first_name="Direct",
    email="direct@example.com",
    ticket_reference="DIRECT-001",
    attended_how="on site",
    hash="DIRECT123",
    uuid="direct-edit-test",
)

# Get background PDF
bg_file = Path(conf.dirs.graphics) / conf.layout.pdf_background.file
output_file = Path("test_direct_edit.pdf")

print("Testing direct edit approach...")
print(f"Background: {bg_file}")
print(f"Output: {output_file}")

# Read the background PDF
reader = PdfReader(str(bg_file))
writer = PdfWriter()

# Get first page
page = reader.pages[0]

# Create a new PDF with just the text using reportlab
packet = io.BytesIO()
can = canvas.Canvas(packet, pagesize=landscape(A4))

# Add text directly - using positions from config
can.setFont("Helvetica-Bold", 24)
can.drawString(50, 595 - 180, attendee.full_name)  # Convert from top-left to bottom-left

can.setFont("Helvetica-Bold", 24)
can.drawString(532, 595 - 128, f"No. {attendee.hash}")

can.save()

# Move to the beginning of the BytesIO buffer
packet.seek(0)
text_pdf = PdfReader(packet)

# Merge the text onto the background page
page.merge_page(text_pdf.pages[0])

# Add the modified page to writer
writer.add_page(page)

# Write output
with open(output_file, "wb") as output:
    writer.write(output)

print(f"✅ Created {output_file}")
print("Check if the text is visible!")

import subprocess

subprocess.run(["open", str(output_file)], check=False)
