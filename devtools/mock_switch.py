"""Development-only Horaco CGI simulator, with no production dependency.

Run: python devtools/mock_switch.py
Use 127.0.0.1:8089 only in a local HA test environment.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from html import escape
import argparse
import time

def table(headers, rows):
    return "<table><tr>" + "".join("<th>"+escape(str(x))+"</th>" for x in headers) + "</tr>" + "".join(
        "<tr>"+"".join("<td>"+escape(str(x))+"</td>" for x in row)+"</tr>" for row in rows
    )+"</table>"

def fixture(path, ports):
    if path == "/info.cgi":
        first = table(["Name", "Value", "Name", "Value"],
                      [["Device Model", "Horaco Test Fixture", "Firmware Version", "simulator-1"],
                       ["MAC Address", "00:11:22:33:44:55", "Sys Uptime", "1Day2Hour"]])
        status = table(["Port", "Link", "Duplex", "Speed", "Flow control"],
                       [[f"Port {n}", "Link Up" if n % 4 else "Link Down", "Full", "1000M" if n < 9 else "10G", "Enabled"]
                        for n in range(1, ports+1)])
        return first + status
    if path == "/port.cgi?page=stats":
        tick = int(time.monotonic())
        return table(["Port", "TxBytes", "RxBytes", "TxGoodPkt", "RxGoodPkt"],
                     [[f"Port {n}", tick*5000*n, tick*3000*n, tick*10*n, tick*8*n] for n in range(1, ports+1)])
    if path == "/port.cgi":
        return table(["Port","State"],[[f"Port {n}","Enable"] for n in range(1,ports+1)])
    if path == "/mac.cgi?page=fwd_tbl":
        return "<span id='totalpage'>1</span>" + table(
            ["MAC Address","Type","Port","VLAN"],
            [["00:11:22:33:44:55","Dynamic","Port 1","10"],
             ["02:11:22:33:44:66","Dynamic","Port 2","20"]])
    if path == "/transceiver.cgi":
        return "<table class='infotbl'><tr><td>Temperature</td><td id='temp'>25-0</td></tr><tr><td>RX Power</td><td id='rxpower'>0-100</td></tr><tr><td>TX Power</td><td id='txpower'>0-210</td></tr><tr><td>Voltage</td><td id='voltage'>12-34</td></tr></table>"
    if path == "/dhcp_snooping.cgi?page=dump":
        return '<input name="enable_dhcpsnp" checked />'
    if path == "/igmp.cgi?page=dump":
        return '<input name="enable_igmp" checked />'
    if path == "/fwd.cgi?page=jumboframe":
        return '<select name="jumboframe"><option selected>9000</option></select>'
    return None

class Handler(BaseHTTPRequestHandler):
    ports = 10
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/login.cgi":
            self.send_html("Login OK")
        elif path == "/mac.cgi":
            self.send_html(fixture("/mac.cgi?page=fwd_tbl", self.ports))
        else:
            self.send_error(405)
    def do_GET(self):
        path = self.path
        result = fixture(path, self.ports)
        if result is None:
            self.send_error(404)
        else:
            self.send_html(result)
    def send_html(self, content):
        payload = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--ports", type=int, default=10)
    args = parser.parse_args()
    Handler.ports = max(1, min(96, args.ports))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Horaco CGI simulator: http://127.0.0.1:{args.port}")
    server.serve_forever()
