"""Read-only parsers based on documented HORACO CGI response layouts."""
import math
from bs4 import BeautifulSoup

def parse_sfp(html):
    soup = BeautifulSoup(html.replace("<th", "<td").replace("</th>", "</td>"), "html.parser")
    table = soup.find("table", class_="infotbl") or soup.find("table")
    if not table:
        raise ValueError("No SFP diagnostics table")
    out = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        key = cells[1].get("id") or cells[0].get_text(" ", strip=True).lower().replace(" ", "_")
        out[key] = cells[1].get_text(" ", strip=True)
    for source, target, scale, power in [
        ("temp", "temperature_c", 0.00391, False),
        ("voltage", "voltage_v", 0.0001, False),
        ("current", "current_ma", 0.002, False),
        ("rxpower", "rx_dbm", 0.0001, True),
        ("txpower", "tx_dbm", 0.0001, True),
    ]:
        raw = out.get(source)
        if not raw:
            continue
        parts = raw.split("-")
        try:
            if len(parts) != 2:
                continue
            value = (int(parts[0]) * 256 + int(parts[1])) * scale
            out[target] = round(10 * math.log10(value), 2) if power and value > 0 else (None if power else round(value, 3))
        except (ValueError, OverflowError):
            continue
    return out

def parse_dhcp(html):
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("input", attrs={"name": "enable_dhcpsnp"})
    if field is None:
        raise ValueError("DHCP snooping page format not recognized")
    ports = {}
    form = soup.find("form", action=lambda v: bool(v and "page=static" in v))
    if form:
        for field in form.find_all("input", class_="chkp"):
            label = form.find("label", attrs={"for": field.get("id")})
            if label:
                ports[label.get_text(" ", strip=True)] = field.has_attr("checked")
    return {"enabled": field.has_attr("checked"), "trusted_ports": ports}

def parse_igmp(html):
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("input", attrs={"name": "enable_igmp"})
    if field is None:
        raise ValueError("IGMP snooping page format not recognized")
    entries = []
    for table in soup.find_all("table"):
        headers = [x.get_text(" ", strip=True).lower() for x in table.find_all("tr")[0].find_all(["td", "th"])] if table.find("tr") else []
        if not (any("ip address" in h for h in headers) and any("vlan" in h for h in headers)):
            continue
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) >= 3:
                entries.append({"ip": cells[0].get_text(strip=True), "ports": cells[1].get_text(strip=True), "vlan": cells[2].get_text(strip=True)})
    return {"enabled": field.has_attr("checked"), "groups": entries}

def parse_jumbo(html):
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("select", attrs={"name": "jumboframe"})
    if field is None:
        raise ValueError("Jumbo frame page format not recognized")
    option = field.find("option", selected=True)
    if option is None:
        option = field.find("option")
    enabled = soup.find("input", attrs={"name": "enable_jumbo"})
    return {"enabled": enabled.has_attr("checked") if enabled else True,
            "size": option.get_text(" ", strip=True) if option else None}
