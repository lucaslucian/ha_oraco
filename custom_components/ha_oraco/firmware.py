"""Read-only firmware version parser; never calls loader or upgrade commands."""
import re
from bs4 import BeautifulSoup

def parse_firmware(html):
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) < 2:
            continue
        if "firmware version" in cells[0].get_text(" ", strip=True).lower():
            version = cells[1].get_text(" ", strip=True)
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+ -]{0,79}", version):
                return {"version": version}
    raise ValueError("Firmware version not found")
