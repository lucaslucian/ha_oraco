"""Require local integration branding at both standard and high-DPI resolutions."""
from pathlib import Path
import struct

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "ha_oraco" / "brand"

def test_png_brand_assets():
    for variant in ("icon", "dark_icon"):
        for suffix, size in (("", (256,256)), ("@2x",(512,512))):
            data = (BRAND / f"{variant}{suffix}.png").read_bytes()
            assert data[:8] == b"\\x89PNG\\r\\n\\x1a\\n"
            assert struct.unpack(">II",data[16:24]) == size
    for variant in ("logo","dark_logo"):
        for suffix, size in (("", (530,130)),("@2x",(1060,260))):
            data=(BRAND / f"{variant}{suffix}.png").read_bytes()
            assert data[:8] == b"\\x89PNG\\r\\n\\x1a\\n"
            assert struct.unpack(">II",data[16:24]) == size
