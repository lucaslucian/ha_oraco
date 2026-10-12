"""Read-only HTTP client for compatible Horaco/OEM Realtek switches."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from urllib.parse import urlsplit
import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)


class SwitchError(Exception):
    """Switch connection or parsing failure."""


class HoracoClient:
    """Single serialized client; no switch configuration methods."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int, username: str, password: str):
        if not re.fullmatch(r"[A-Za-z0-9.:\-]+", host) or "/" in host:
            raise ValueError("Invalid switch host")
        self.host = host
        self.base = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self.session = session
        self.lock = asyncio.Lock()
        self.cookie = {}
        self.logged_in = False

    async def _login(self):
        digest = hashlib.md5((self.username + self.password).encode()).hexdigest()
        data = {"username": self.username, "password": self.password, "Response": digest, "language": "EN"}
        async with self.session.post(self.base + "/login.cgi", data=data, headers={"Referer": self.base + "/login.html"}, allow_redirects=True,
                                     timeout=aiohttp.ClientTimeout(total=20)) as response:
            if response.status != 200:
                raise SwitchError(f"Login HTTP {response.status}")
            self.cookie = {"admin": digest}
            self.logged_in = True

    async def get(self, path: str) -> str:
        """Permit only approved monitoring GET requests."""
        if path not in ("/info.cgi", "/port.cgi", "/port.cgi?page=stats", "/mac.cgi?page=fwd_tbl", "/transceiver.cgi", "/dhcp_snooping.cgi?page=dump", "/igmp.cgi?page=dump", "/fwd.cgi?page=jumboframe", "/vlan.cgi?page=port_based", "/port.cgi?page=isolation", "/loop.cgi?page=stp_port", "/fwd.cgi?page=storm_ctrl", "/loop.cgi?page=stp_global", "/trunk.cgi?page=group"):
            raise SwitchError("Unapproved read endpoint")
        async with self.lock:
            if not self.logged_in:
                await self._login()
            await asyncio.sleep(0.4)
            for attempt in range(2):
                async with self.session.get(self.base + path, cookies=self.cookie, headers={"Referer": self.base + "/"}, allow_redirects=True,
                                            timeout=aiohttp.ClientTimeout(total=20)) as response:
                    if response.status in (401, 403) and attempt == 0:
                        self.logged_in = False
                        await self._login()
                        continue
                    if response.status != 200:
                        raise SwitchError(f"GET {path}: HTTP {response.status}")
                    text = await response.text(errors="replace")
                    if re.search(r"<form[^>]+(?:login|password)", text, re.I) and attempt == 0:
                        self.logged_in = False
                        await self._login()
                        continue
                    return text
            raise SwitchError("Authentication expired")


    async def mac_page(self, page: int) -> str:
        """Read-only MAC pagination; recover expired authentication once."""
        if not 2 <= page <= 100:
            raise SwitchError("Invalid MAC table page")
        async with self.lock:
            if not self.logged_in:
                await self._login()
            await asyncio.sleep(0.4)
            for attempt in range(2):
                async with self.session.post(
                    self.base + "/mac.cgi?page=fwd_tbl",
                    data={"cmd": "goto", "pageidx": str(page), "perpage": "3"},
                    cookies=self.cookie,
                    headers={"Referer": self.base + "/mac.cgi?page=fwd_tbl"},
                    allow_redirects=True,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as response:
                    if response.status in (401, 403) and attempt == 0:
                        self.logged_in = False
                        await self._login()
                        continue
                    if response.status != 200:
                        raise SwitchError(f"MAC pagination HTTP {response.status}")
                    body = await response.text(errors="replace")
                    if re.search(r"<form[^>]+(?:login|password)", body, re.I):
                        if attempt == 0:
                            self.logged_in = False
                            await self._login()
                            continue
                        raise SwitchError("MAC pagination authentication expired")
                    return body
            raise SwitchError("MAC pagination authentication expired")


def _value(cell):
    return cell.get_text(" ", strip=True)


def parse_info(html: str) -> tuple[dict, dict]:
    """Read operational status from the switch overview, including form-embedded name."""
    soup = BeautifulSoup(html, "html.parser")
    device = {}
    ports = {}
    mappings = {
        "device name": "name", "device model": "model",
        "sys uptime": "uptime", "system uptime": "uptime",
        "firmware version": "firmware", "firmware": "firmware",
        "mac address": "mac", "ip address": "ip_address", "netmask": "netmask",
    }
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            # Overview firmware has two label/value pairs per row.
            for index in range(0, len(cells) - 1, 2):
                label = _value(cells[index]).lower().strip().rstrip(":")
                key = mappings.get(label)
                if key is None:
                    continue
                cell = cells[index + 1]
                field = cell.find("input", attrs={"name": "devName"})
                value = field.get("value", "").strip() if field else _value(cell)
                if value:
                    if key == "uptime":
                        duration = re.fullmatch(r"(\d+)Day(\d+)Hour(\d+)Minute(\d+)Second", value, re.I)
                        if duration:
                            days, hours, minutes, seconds = map(int, duration.groups())
                            device["uptime_raw"] = value
                            device["uptime_seconds"] = days * 86400 + hours * 3600 + minutes * 60 + seconds
                            readable = [f"{n} {unit}" for n, unit in
                                        ((days, "d"), (hours, "h"), (minutes, "min"), (seconds, "s"))
                                        if n]
                            value = " ".join(readable) or "0 s"
                    device[key] = value
        header = table.find("tr")
        if header is None:
            continue
        headings = [_value(c).lower() for c in header.find_all(["th", "td"], recursive=False)]
        if not ("port" in headings and any("link status" in h for h in headings)):
            continue
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td", recursive=False)
            if len(cells) < 4:
                continue
            match = re.fullmatch(r"port\s+(\d+)", _value(cells[0]), re.I)
            if not match:
                continue
            n = match.group(1)
            link = _value(cells[1])
            ports[n] = {"port": n, "up": link.lower() == "link up", "link": link,
                        "duplex": _value(cells[2]), "speed": _value(cells[3]),
                        "flow_control": _value(cells[4]) if len(cells) > 4 else ""}
    return device, ports


def parse_stats(html: str) -> dict:
    """Only report counters actually provided by firmware; never invent byte counts."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [_value(c).lower().replace(" ", "").replace("_", "") for c in rows[0].find_all(["th", "td"])]
        if not any("pkt" in h or "byte" in h or "octet" in h for h in headers):
            continue
        fields = {}
        for idx, name in enumerate(headers):
            direction = "tx" if "tx" in name else "rx" if "rx" in name else None
            kind = "bytes" if ("byte" in name or "octet" in name) else "packets" if ("pkt" in name or "packet" in name) else None
            if direction and kind:
                fields[f"{direction}_{kind}"] = idx
        result = {}
        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue
            match = re.search(r"(?:port\s*)?(\d+)", _value(cells[0]), re.I)
            if not match:
                continue
            item = {}
            for field, idx in fields.items():
                if idx >= len(cells):
                    continue
                raw = _value(cells[idx]).replace(",", "")
                try:
                    if "-" in raw and len(raw.split("-")) == 2:
                        high, low = (int(x) for x in raw.split("-"))
                        if not (0 <= high <= 0xFFFFFFFF and 0 <= low <= 0xFFFFFFFF):
                            continue
                        item[field] = high * (2**32) + low
                    else:
                        value = int(raw, 0) if raw.lower().startswith("0x") else int(raw)
                        if not 0 <= value < 2**64:
                            continue
                        item[field] = value
                except ValueError:
                    pass
            result[match.group(1)] = item
        return result
    return {}
