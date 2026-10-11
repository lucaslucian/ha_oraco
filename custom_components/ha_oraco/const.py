"""Integration constants. HTTP interface, read-only endpoints only."""
DOMAIN = "ha_oraco"
DEFAULT_PORT = 80
DEFAULT_USER = "admin"
INTERVALS = {"fast": 30, "optics": 60, "mac": 120, "network": 300, "vlans": 600, "device": 3600, "static": 21600}
# These are known read-only CGI pages; additional firmware endpoints require verification.
INFO = "/info.cgi"
STATS = "/port.cgi?page=stats"
PORTS = "/port.cgi"
LOGIN = "/login.cgi"
