#!/usr/bin/env python
"""Convert PDF background to PNG image for use as background"""

import subprocess
from pathlib import Path

pdf_path = Path("graphics/EuroScipy-2025-Certificate-of-Attendance.pdf")
png_path = Path("graphics/EuroScipy-2025-Certificate-of-Attendance.png")

if pdf_path.exists():
    print(f"Converting {pdf_path} to PNG...")

    # Use sips (macOS built-in) to convert PDF to PNG
    # Alternative: Install pdf2image with: pip install pdf2image
    try:
        # Try with sips (macOS)
        result = subprocess.run(
            ["sips", "-s", "format", "png", str(pdf_path), "--out", str(png_path)],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print(f"✓ Created {png_path}")
        else:
            print(f"✗ sips failed: {result.stderr}")

            # Try with ImageMagick convert if available
            print("\nTrying with ImageMagick convert...")
            result2 = subprocess.run(
                [
                    "convert",
                    "-density",
                    "150",
                    str(pdf_path) + "[0]",  # First page only
                    str(png_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if result2.returncode == 0:
                print(f"✓ Created {png_path} with ImageMagick")
            else:
                print(f"✗ ImageMagick failed: {result2.stderr}")
                print("\nPlease convert the PDF to PNG manually or install pdf2image")

    except FileNotFoundError as e:
        print(f"Command not found: {e}")
        print("\nTo convert PDF to image, you can:")
        print("1. Open the PDF in Preview and export as PNG")
        print("2. Install pdf2image: pip install pdf2image")
        print("3. Use online converter")
else:
    print(f"PDF not found: {pdf_path}")
