"""Read-only parsers for switch protection status tables."""
import re
from bs4 import BeautifulSoup


def _port(value):
    match = re.fullmatch(r"\s*Port\s+(\d+)\s*", value, re.I)
    return match.group(1) if match else None


def _status_table(soup, required_headers):
    """Select a populated status table, even if firmware wraps it in a POST form.

    A status table must have concrete port rows and cannot contain editable controls.
    """
    candidates = []
    for table in soup.find_all("table"):
        if table.find(["input", "select", "textarea", "button"]):
            continue
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all(["th", "td"])]
        if not all(any(term in h for h in headers) for term in required_headers):
            continue
        valid_rows = sum(1 for row in rows[1:] if row.find("td") and
                         _port(row.find("td").get_text(" ", strip=True)))
        if valid_rows:
            candidates.append((table.find_parent("form") is not None, -valid_rows, table))
    if candidates:
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]
    raise ValueError("Protection status table not found")


def _port_ranges(value):
    """Expand an isolation list such as '1-9,11' without presuming isolation semantics."""
    value = value.strip()
    if not re.fullmatch(r"[\d\s,;\-]+", value):
        raise ValueError("Unsupported isolation list format")
    ports = set()
    for part in re.split(r"[,;]", value):
        part = part.strip()
        if not part:
            continue
        match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if match:
            start, end = map(int, match.groups())
            if start > end or end - start > 256:
                raise ValueError("Invalid isolation range")
            ports.update(range(start, end + 1))
        elif part.isdigit():
            ports.add(int(part))
        else:
            raise ValueError("Invalid isolation port")
    return sorted(ports)


def parse_isolation(html):
    """Capture the firmware's isolation list; it does not prove forwarding direction."""
    soup = BeautifulSoup(html, "html.parser")
    table = _status_table(soup, ("port", "isolation list"))
    result = {}
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        number = _port(cells[0].get_text(" ", strip=True))
        if not number:
            continue
        raw = cells[1].get_text(" ", strip=True)
        result[number] = {"port": number, "raw_list": raw, "listed_ports": _port_ranges(raw)}
    if not result:
        raise ValueError("No isolation status rows")
    return {"ports": result, "meaning": "firmware_isolation_list"}


def parse_stp_ports(html):
    """Parse the *displayed* STP rows, never the editable default form."""
    soup = BeautifulSoup(html, "html.parser")
    # Status table uses spanning header groups and 10 cells per data row.
    for table in soup.find_all("table"):
        if table.find_parent("form") is not None:
            continue
        rows = table.find_all("tr")
        header = " ".join(c.get_text(" ", strip=True).lower() for c in rows[0].find_all("th")) if rows else ""
        if "path cost" not in header or "role" not in header or "state" not in header:
            continue
        result = {}
        for row in rows[2:]:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 10:
                continue
            number = _port(cells[0].get_text(" ", strip=True))
            if not number:
                continue
            values = [cell.get_text(" ", strip=True) for cell in cells]
            result[number] = dict(port=number, state=values[1], role=values[2],
                path_cost_config=values[3], path_cost_actual=values[4],
                priority=values[5], p2p_config=values[6], p2p_actual=values[7],
                edge_config=values[8], edge_actual=values[9])
        if result:
            return {"ports": result}
    raise ValueError("STP port status table missing")


def parse_storm_control(html):
    """Report four per-port thresholds from the displayed read-only summary."""
    soup = BeautifulSoup(html, "html.parser")
    table = _status_table(soup, ("port", "broadcast rate", "known multicast", "unknown multicast", "unknown unicast"))
    rows = table.find_all("tr")
    keys = ["broadcast_kbps", "known_multicast_kbps", "unknown_multicast_kbps", "unknown_unicast_kbps"]
    ports = {}
    for row in rows[1:]:
        cells = row.find_all("td", recursive=False)
        if len(cells) < 5:
            continue
        number = _port(cells[0].get_text(" ", strip=True))
        if not number:
            continue
        values = []
        for cell in cells[1:5]:
            raw = cell.get_text(" ", strip=True)
            if raw.lower() == "off":
                values.append(None)
            elif raw.isdecimal():
                values.append(int(raw))
            else:
                raise ValueError("Unknown storm control threshold")
        ports[number] = dict(port=number, **dict(zip(keys, values)))
    if not ports:
        raise ValueError("No storm control port status rows")
    return {"ports": ports}
