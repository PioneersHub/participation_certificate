#!/usr/bin/env python
"""Test using fpdf2 with PDF template - the simplest approach"""

from pathlib import Path

from fpdf import FPDF

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
    uuid="template-test",
)

# Get background PDF
bg_file = Path(conf.dirs.graphics) / conf.layout.pdf_background.file
output_file = Path("test_fpdf_template.pdf")

print("Testing fpdf2 template approach (simplest solution)...")
print(f"Background: {bg_file}")
print(f"Attendee: {attendee.full_name}")

# Create PDF and use the background as a template
pdf = FPDF(format="A4", orientation="L", unit="pt")

# Try the set_page_background approach - fpdf2 supports this!
pdf.add_page()

# Set the background PDF for this page
pdf.set_page_background(str(bg_file))

# Now just add text normally - it will appear on top of the background!
# Load fonts - need all variants for markdown
pdf.add_font("poppins-bold", "", "fonts/Poppins/Poppins-Bold.ttf")
pdf.add_font("poppins-regular", "", "fonts/Poppins/Poppins-Regular.ttf")
pdf.add_font("poppins-regular", "B", "fonts/Poppins/Poppins-Bold.ttf")  # Bold variant
pdf.add_font("poppins-regular", "I", "fonts/Poppins/Poppins-Italic.ttf")  # Italic variant

# Add the attendee name
pdf.set_font("poppins-bold", size=24)
pdf.set_xy(50, 180)
pdf.cell(text=attendee.full_name)

# Add the hash
pdf.set_xy(532, 128)
pdf.cell(text=f"No. {attendee.hash}")

# Add the multi-line text
pdf.set_font("poppins-regular", size=16)
pdf.set_xy(45, 200)
text = f"has attended the **PyCon DE & PyData 2025**\nconference {attendee.attended_how}."
pdf.multi_cell(w=600, text=text, markdown=True)

# Save
pdf.output(output_file)

print(f"✅ Created {output_file}")
print("This should have the background with visible text on top!")

import subprocess

subprocess.run(["open", str(output_file)], check=False)
