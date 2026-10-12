"""Parse the switch's read-only VLAN port overview without touching configuration forms."""
import re
from bs4 import BeautifulSoup

def _ids(value):
    return sorted({int(n) for n in re.findall(r"\b\d{1,4}\b", value or "") if 1 <= int(n) <= 4094})

def parse_port_vlans(html):
    """Read only the displayed status table (.showdiv), never edit-form defaults.

    Absence of a VLAN in the page is not evidence of a disabled VLAN.
    """
    soup = BeautifulSoup(html, "html.parser")
    area = soup.select_one(".showdiv")
    if not area:
        raise ValueError("VLAN status table missing")
    table = area.find("table")
    if table is None:
        raise ValueError("VLAN status table missing")
    rows = table.find_all("tr")
    if not rows:
        raise ValueError("VLAN status table empty")
    headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
    port_i = next((i for i, h in enumerate(headers) if h == "port"), None)
    type_i = next((i for i, h in enumerate(headers) if "vlan type" in h), None)
    access_i = next((i for i, h in enumerate(headers) if "access vlan" in h), None)
    native_i = next((i for i, h in enumerate(headers) if "native vlan" in h), None)
    trunk_i = next((i for i, h in enumerate(headers) if "trunk vlan" in h), None)
    if port_i is None or type_i is None:
        raise ValueError("Unrecognized VLAN table columns")

    def col(cells, idx):
        return cells[idx].get_text(" ", strip=True) if idx is not None and idx < len(cells) else ""

    result = {}
    for tr in rows[1:]:
        cells = tr.find_all("td", recursive=False)
        if len(cells) <= max(port_i, type_i):
            continue
        port_match = re.search(r"\b(?:port\s*)?(\d+)\b", col(cells, port_i), re.I)
        if not port_match:
            continue
        num = port_match.group(1)
        raw_type = col(cells, type_i)
        kind = raw_type.split(":", 1)[0].strip().lower()
        if kind not in ("access", "trunk", "hybrid"):
            kind = "unknown"
        accepted = raw_type.split(":", 1)[1].strip() if ":" in raw_type else None
        access_ids = _ids(col(cells, access_i))
        native_ids = _ids(col(cells, native_i))
        trunk_cell = cells[trunk_i] if trunk_i is not None and trunk_i < len(cells) else None
        tagged = []
        untagged = []
        allowed = []
        if trunk_cell is not None:
            chunks = trunk_cell.select(".vlancontent")
            if chunks:
                for chunk in chunks:
                    text = chunk.get_text(" ", strip=True)
                    if re.match(r"^tagged\s+vlan\s*:", text, re.I):
                        tagged.extend(_ids(text.split(":", 1)[1]))
                    elif re.match(r"^untagged\s+vlan\s*:", text, re.I):
                        untagged.extend(_ids(text.split(":", 1)[1]))
            else:
                allowed = _ids(trunk_cell.get_text(" ", strip=True))
        # Do not imply that native VLAN is explicitly tagged/untagged unless reported.
        result[num] = {
            "port": num, "mode": kind, "accepted_frames": accepted,
            "access_vlan": access_ids[0] if access_ids else None,
            "native_vlan": native_ids[0] if native_ids else None,
            "allowed_vlans": sorted(set(allowed)),
            "tagged_vlans": sorted(set(tagged)),
            "untagged_vlans": sorted(set(untagged)),
        }
    if not result:
        raise ValueError("No VLAN ports in status table")
    return {"ports": result, "port_count": len(result)}
