"""Read-only switch status parsing."""
from bs4 import BeautifulSoup

def parse_stp_global(html):
    soup = BeautifulSoup(html, 'html.parser')
    result = {}
    for row in soup.find_all('tr'):
        cells = row.find_all(['td', 'th'], recursive=False)
        if len(cells) != 2:
            continue
        key = cells[0].get_text(' ', strip=True).lower()
        value = cells[1].get_text(' ', strip=True)
        if key == 'spanning tree status':
            result['enabled'] = value.lower() in ('enable', 'enabled')
            result['status'] = value
        elif key.startswith('root '):
            result[key.replace(' ', '_')] = value
    if 'enabled' not in result:
        raise ValueError('STP status unavailable')
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
