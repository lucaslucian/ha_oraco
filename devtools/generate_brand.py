"""Generate local PNG brand images from the canonical vector assets.

Run: python devtools/generate_brand.py
Dependencies: cairosvg, Pillow
"""
from pathlib import Path
from io import BytesIO
import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "custom_components" / "ha_oraco" / "brand"
TARGET.mkdir(parents=True, exist_ok=True)

def render(source, target, size):
    svg = (ROOT / "assets" / source).read_bytes()
    png = cairosvg.svg2png(bytestring=svg, output_width=size[0], output_height=size[1])
    image = Image.open(BytesIO(png)).convert("RGBA")
    image.save(TARGET / target, format="PNG", optimize=True)
    print(f"{target}: {image.width}x{image.height}")

render("icon.svg", "icon.png", (256,256))
render("icon.svg", "icon@2x.png", (512,512))
render("icon.svg", "dark_icon.png", (256,256))
render("icon.svg", "dark_icon@2x.png", (512,512))
render("logo.svg", "logo.png", (530,130))
render("logo.svg", "logo@2x.png", (1060,260))
render("logo.svg", "dark_logo.png", (530,130))
render("logo.svg", "dark_logo@2x.png", (1060,260))
