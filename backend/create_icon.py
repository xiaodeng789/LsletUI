#!/usr/bin/env python3
"""Create .ico file from SVG for Nuitka packaging"""
import sys
import os

try:
    from PIL import Image
    import cairosvg
    from io import BytesIO
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Installing dependencies...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "cairosvg"])
    from PIL import Image
    import cairosvg
    from io import BytesIO

# SVG file path
svg_path = os.path.join(os.path.dirname(__file__), "img", "default_icon.svg")
ico_path = os.path.join(os.path.dirname(__file__), "img", "default_icon.ico")

# Convert SVG to PNG in memory
png_data = cairosvg.svg2png(url=svg_path, output_width=256, output_height=256)

# Create image from PNG data
img = Image.open(BytesIO(png_data))

# Save as .ico with multiple sizes
img.save(ico_path, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print(f"Successfully created: {ico_path}")