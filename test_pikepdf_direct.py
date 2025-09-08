#!/usr/bin/env python
"""Test directly adding text to background PDF using pikepdf"""

import shutil
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, Stream

from participation_certificate import conf
from participation_certificate.preprocess_attendees import Attendee

# Test attendee
attendee = Attendee(
    full_name="Alexander CS Hendorf",
    first_name="Alexander",
    email="direct@example.com",
    ticket_reference="DIRECT-001",
    attended_how="on site",
    hash="ALEX2025",
    uuid="pikepdf-direct-test",
)

# Get background PDF
bg_file = Path(conf.dirs.graphics) / conf.layout.pdf_background.file
output_file = Path("test_pikepdf_direct.pdf")

print("Testing pikepdf direct text approach...")
print(f"Background: {bg_file}")
print(f"Attendee: {attendee.full_name}")
print(f"Output: {output_file}")

# Copy background to output
shutil.copy(bg_file, output_file)

# Open the PDF for editing
pdf = pikepdf.open(output_file, allow_overwriting_input=True)
page = pdf.pages[0]

# Page dimensions (A4 landscape: 842 x 595 points)
page_height = 595

# Create a content stream to add text
# We need to build a proper text object in PDF format
text_operations = []

# Add font setup
text_operations.append("BT")  # Begin text

# Position for name (from config: x=50, y=180)
# PDF coordinates are from bottom-left, config is from top-left
y_from_bottom = page_height - 180
text_operations.append(f"1 0 0 1 50 {y_from_bottom} Tm")  # Text matrix positioning

# Set font (using Helvetica-Bold, size 24)
text_operations.append("/Helvetica-Bold 24 Tf")  # Font and size

# Draw the text
text_operations.append(f"({attendee.full_name}) Tj")  # Show text

# Position for hash (from config: x=532, y=128)
y_from_bottom_hash = page_height - 128
text_operations.append(f"1 0 0 1 532 {y_from_bottom_hash} Tm")  # Move to hash position
text_operations.append(f"(No. {attendee.hash}) Tj")  # Show hash

text_operations.append("ET")  # End text

# Join all operations
content_stream = " ".join(text_operations)

# Add the content stream to the page
# This is tricky - we need to append to existing content
if hasattr(page, "Contents"):
    if isinstance(page.Contents, list):
        # Multiple content streams
        new_stream = Stream(pdf, content_stream.encode())
        page.Contents.append(new_stream)
    else:
        # Single content stream - convert to array and add new
        existing = page.Contents
        new_stream = Stream(pdf, content_stream.encode())
        page.Contents = Array([existing, new_stream])
else:
    # No content (unlikely for a background PDF)
    page.Contents = Stream(pdf, content_stream.encode())

# Ensure fonts are available
if "/Font" not in page.Resources:
    page.Resources["/Font"] = Dictionary()

# Add Helvetica-Bold to resources if not present
if "/Helvetica-Bold" not in page.Resources["/Font"]:
    page.Resources["/Font"]["/Helvetica-Bold"] = Dictionary(
        Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/Helvetica-Bold")
    )

# Save the modified PDF
pdf.save(output_file)
pdf.close()

print(f"✅ Created {output_file}")
print("Opening PDF to check if text is visible...")

import subprocess

subprocess.run(["open", str(output_file)], check=False)
