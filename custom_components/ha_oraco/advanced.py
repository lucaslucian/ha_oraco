"""Read-only parsers based on documented HORACO CGI response layouts."""
import math
import re
from bs4 import BeautifulSoup

def parse_sfp(html):
    """Decode DDMI values when raw counters are present; retain other readable fields.

    Unreported or zero optical power is unknown, not a measured -40 dBm.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="infotbl") or soup.find("table")
    if not table:
        title = soup.title.get_text(" ", strip=True)[:60] if soup.title else "sem título"
        raise ValueError(f"SFP response contains no table (title={title!r})")
    raw = {}
    aliases = {
        "temp": "temperature_c", "temperature": "temperature_c",
        "voltage": "voltage_v", "current": "current_ma",
        "rxpower": "rx_dbm", "rx_power": "rx_dbm",
        "txpower": "tx_dbm", "tx_power": "tx_dbm",
        "vendorname": "vendor", "vendor_name": "vendor",
        "vendor": "vendor", "partnumber": "part_number",
        "part_number": "part_number", "serialnumber": "serial_number",
        "serial_number": "serial_number", "wavelength": "wavelength_nm",
    }
    # This firmware emits malformed markup: several <th> elements end with
    # </td> and the initial Port row lacks its opening <tr>. BeautifulSoup's
    # html.parser nests these cells and yields no direct th/td pairs.
    # Extract the narrow label/value pattern from the original table HTML.
    # Use original source: BeautifulSoup may restructure malformed cell closures.
    table_html = html
    for match in re.finditer(
        r"<th\b[^>]*>(.*?)</(?:th|td)\s*>\s*<td\b([^>]*)>(.*?)</td\s*>",
        table_html, re.I | re.S,
    ):
        label = BeautifulSoup(match.group(1), "html.parser").get_text(" ", strip=True)
        td_attrs = match.group(2)
        value = BeautifulSoup(match.group(3), "html.parser").get_text(" ", strip=True)
        identity = re.search(r'\bid\s*=\s*["\\\']?([\\w-]+)', td_attrs, re.I)
        key = (identity.group(1) if identity else label).strip().lower().replace(" ", "_").replace("-", "_")
        if key:
            raw[key] = value
    # Also accept correctly structured tables from other firmware versions.
    if not raw:
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"], recursive=False)
            if len(cells) < 2:
                continue
            key = cells[1].get("id") or cells[0].get_text(" ", strip=True)
            key = key.strip().lower().replace(" ", "_").replace("-", "_")
            raw[key] = cells[1].get_text(" ", strip=True)
    out = {}
    ddmi = {
        "temp": ("temperature_c", 1 / 256, False, True),
        "voltage": ("voltage_v", 0.0001, False, False),
        "current": ("current_ma", 0.002, False, False),
        "rxpower": ("rx_dbm", 0.0001, True, False),
        "txpower": ("tx_dbm", 0.0001, True, False),
    }
    for key, value in raw.items():
        normalized = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        mapping = {"oe_present":"module_present","loss_of_signal":"loss_of_signal",
            "transceiver_type":"transceiver","connector_type":"connector",
            "eth_compliance_codes":"compliance","transmission_media":"media",
            "vendor_oui":"vendor_oui","vendor_pn":"part_number",
            "vendor_revision":"revision","vendor_sn":"serial_number",
            "date_code":"manufacture_date","temperature_c":"temperature_c",
            "voltage_v":"voltage_v","current_ma":"current_ma",
            "output_power_dbm":"tx_dbm","input_power_dbm":"rx_dbm",
            "wavelength":"wavelength_nm","vendor_name":"vendor"}
        field = mapping.get(normalized, aliases.get(key, normalized))
        parts = value.split("-")
        raw_kind = key if key in ddmi else {"temperature_c":"temp",
            "voltage_v":"voltage","current_ma":"current",
            "tx_dbm":"txpower","rx_dbm":"rxpower"}.get(field)
        if raw_kind in ddmi and len(parts) == 2 and all(part.strip().isdigit() for part in parts):
            name, scale, optical, signed = ddmi[raw_kind]
            high, low = int(parts[0]), int(parts[1])
            if not (0 <= high <= 255 and 0 <= low <= 255):
                out[field] = None
                continue
            count = high * 256 + low
            if signed and count >= 32768:
                count -= 65536
            measured = count * scale
            if optical:
                out[field] = round(10 * math.log10(measured), 2) if measured > 0 else None
            else:
                out[field] = round(measured, 3)
        elif field in ("temperature_c", "voltage_v", "current_ma", "rx_dbm", "tx_dbm"):
            # Some firmware revisions already expose human-readable values.
            # Numeric zero optical power usually means no signal, not -40 dBm.
            match = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*(?:°C|C|V|mA|dBm)?\s*", value, re.I)
            if match:
                number = float(match.group(1))
                out[field] = None if field in ("rx_dbm", "tx_dbm") and number == 0 else number
            else:
                out[field] = None
        else:
            out[field] = value
    if not any(k in out for k in ("module_present", "temperature_c", "vendor", "transceiver", "rx_dbm", "tx_dbm", "voltage_v", "current_ma")):
        title = soup.title.get_text(" ", strip=True)[:60] if soup.title else "sem título"
        labels = [re.sub(r"[^a-z0-9]+", "_", k).strip("_") for k in raw.keys()]
        # Only expose page structure, never response HTML/cookies/credentials.
        raise ValueError(
            f"Unexpected SFP page (title={title!r}, rows={len(raw)}, "
            f"labels={','.join(labels[:8])!r})"
        )
    return out

def _table_headers(table):
    rows=table.find_all("tr")
    if not rows:
        return [], []
    headers=[c.get_text(" ",strip=True).lower()
             for c in rows[0].find_all(["th","td"],recursive=False)]
    return headers,rows[1:]


def _port_numbers(value):
    """Accept unambiguous enumerated port lists, never infer unknown formats."""
    cleaned=re.sub(r"(?i)\bports?\b", "", str(value or "")).strip()
    if not cleaned or not re.fullmatch(r"\d+(?:\s*[,;/ ]\s*\d+)*",cleaned):
        return []
    return list(dict.fromkeys(str(int(v)) for v in re.findall(r"\d+",cleaned)
                              if 1<=int(v)<=256))


def parse_dhcp(html):
    """Only explicit, readable trust status is reported per port.

    Checkboxes from 'page=static' are static-binding form controls, not
    evidence that an interface is trusted.
    """
    soup = BeautifulSoup(html, "html.parser")
    enabled_field = soup.find("input", attrs={"name": "enable_dhcpsnp"})
    if enabled_field is None:
        raise ValueError("DHCP snooping page format not recognized")
    trusted={}
    details={}
    for table in soup.find_all("table"):
        if table.find(["input","select","textarea"]):
            continue
        headers,rows=_table_headers(table)
        port_col=next((i for i,h in enumerate(headers) if h in ("port","interface","port number")),None)
        trust_col=next((i for i,h in enumerate(headers) if "trust" in h),None)
        if port_col is None or trust_col is None:
            continue
        for row in rows:
            cells=row.find_all("td",recursive=False)
            if max(port_col,trust_col)>=len(cells):
                continue
            ports=_port_numbers(cells[port_col].get_text(" ",strip=True))
            trust=cells[trust_col].get_text(" ",strip=True).lower()
            if trust not in ("trusted","untrusted","yes","no","enabled","disabled","on","off"):
                continue
            for number in ports:
                trusted[number]=trust in ("trusted","yes","enabled","on")
                details[number]={"trusted":trusted[number],"source":"observed_status_table"}
    return {"enabled": enabled_field.has_attr("checked"),
            "trusted_ports":trusted,"per_port":details,
            "trust_status_available":bool(details)}


def parse_igmp(html):
    soup = BeautifulSoup(html, "html.parser")
    field = soup.find("input", attrs={"name": "enable_igmp"})
    if field is None:
        raise ValueError("IGMP snooping page format not recognized")
    entries=[]
    per_port={}
    for table in soup.find_all("table"):
        headers,rows=_table_headers(table)
        ip_col=next((i for i,h in enumerate(headers) if "ip address" in h or "group address" in h),None)
        vlan_col=next((i for i,h in enumerate(headers) if "vlan" in h),None)
        port_col=next((i for i,h in enumerate(headers) if "port" in h),None)
        if None in (ip_col,vlan_col,port_col):
            continue
        for row in rows:
            cells=row.find_all("td",recursive=False)
            if max(ip_col,vlan_col,port_col)>=len(cells):
                continue
            ip=cells[ip_col].get_text(" ",strip=True)
            vlan=cells[vlan_col].get_text(" ",strip=True)
            raw_ports=cells[port_col].get_text(" ",strip=True)
            numbers=_port_numbers(raw_ports)
            if not ip or not vlan:
                continue
            item={"ip":ip,"vlan":vlan,"ports":raw_ports,
                  "port_numbers":numbers}
            entries.append(item)
            for number in numbers:
                per_port.setdefault(number,[]).append({"group":ip,"vlan":vlan})
    return {"enabled":field.has_attr("checked"),"groups":entries,
            "per_port":per_port,"per_port_available":bool(per_port)}


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
