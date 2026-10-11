"""MAC address helpers for HORACO switch forwarding-table monitoring."""
import re
from bs4 import BeautifulSoup

def normalize_mac(value: str) -> str | None:
    raw = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
    if len(raw) != 12:
        return None
    return ":".join(raw[i:i+2] for i in range(0, 12, 2))

def mac_classification(mac: str) -> str:
    first = int(mac[:2], 16)
    if first & 1:
        return "multicast"
    if first & 2:
        return "locally_administered"
    return "globally_administered"

def parse_mac_page(html: str):
    soup = BeautifulSoup(html, "html.parser")
    pages = soup.find(id="totalpage")
    count = min(100, max(1, int(pages.get_text(strip=True)))) if pages and pages.get_text(strip=True).isdigit() else 1
    entries = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [x.get_text(strip=True).lower() for x in rows[0].find_all(["th", "td"])]
        mac_i = next((i for i, h in enumerate(headers) if "mac" in h), -1)
        port_i = next((i for i, h in enumerate(headers) if "port" in h), -1)
        if mac_i < 0 or port_i < 0:
            continue
        vlan_i = next((i for i, h in enumerate(headers) if "vlan" in h), -1)
        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) <= max(mac_i, port_i):
                continue
            mac = normalize_mac(cells[mac_i].get_text(strip=True))
            if mac:
                entries.append({"mac": mac, "port": cells[port_i].get_text(strip=True),
                                "vlan": cells[vlan_i].get_text(strip=True) if 0 <= vlan_i < len(cells) else None,
                                "classification": mac_classification(mac)})
        break
    return entries, count
