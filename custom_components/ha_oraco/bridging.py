"""Read-only switch status parsing."""
from bs4 import BeautifulSoup

def parse_stp_global(html):
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    names = {
        "spanning tree status": "status", "version": "version",
        "priority": "priority", "max aging time": "max_age",
        "hello time": "hello_time", "forward delay": "forward_delay",
        "root priority": "root_priority", "root mac address": "root_mac",
        "root path cost": "root_path_cost", "root port": "root_port",
        "root maximum age": "root_max_age", "root hello time": "root_hello_time",
        "root forward delay": "root_forward_delay",
    }
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if len(cells) != 2:
            continue
        key = names.get(cells[0].get_text(" ", strip=True).lower())
        if key is None:
            continue
        select = cells[1].find("select")
        field = cells[1].find("input")
        if select:
            option = select.find("option", selected=True)
            value = option.get_text(" ", strip=True) if option else None
        elif field:
            value = field.get("value")
        else:
            value = cells[1].get_text(" ", strip=True)
        result[key] = value
    if not result.get("status"):
        raise ValueError("STP status unavailable")
    result["enabled"] = result["status"].lower() in ("enable", "enabled")
    return result

def parse_aggregation(html):
    soup = BeautifulSoup(html, 'html.parser')
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        header = rows[0].get_text(' ', strip=True).lower()
        if 'aggregate group id' not in header or 'member port' not in header:
            continue
        groups = []
        for row in rows[1:]:
            cells = row.find_all('td', recursive=False)
            if len(cells) >= 5:
                groups.append({'group': cells[1].get_text(' ', strip=True), 'type': cells[2].get_text(' ', strip=True), 'members': cells[3].get_text(' ', strip=True), 'aggregated_port': cells[4].get_text(' ', strip=True)})
        return {'groups': groups, 'count': len(groups)}
    raise ValueError('Aggregation table unavailable')
