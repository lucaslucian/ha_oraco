"""Evidence-based layer-2 topology model from forwarding-table observations."""

def build_topology(host, ports, entries):
    """Connections to MACs are observed, physical intermediate links are not inferred."""
    nodes = [{"id": "switch", "label": "Horaco " + host, "kind": "switch"}]
    edges = []
    for number, port in sorted(ports.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 999):
        port_id = "port:" + str(number)
        nodes.append({"id": port_id, "label": "Porta " + str(number),
                      "kind": "port", "up": bool(port.get("up")), "speed": port.get("speed")})
        edges.append({"from": "switch", "to": port_id, "relation": "physical_port", "confidence": "confirmed"})
    seen = set()
    for row in entries:
        mac = row.get("mac")
        if not mac:
            continue
        port = str(row.get("port", "")).strip()
        import re
        match = re.search(r"\d+", port)
        if not match:
            continue
        number = match.group()
        if number not in ports:
            continue
        key = (mac, str(row.get("vlan") or ""))
        if key in seen:
            continue
        seen.add(key)
        node_id = "mac:" + "|".join(key)
        nodes.append({"id": node_id, "label": row.get("name") or mac,
                      "kind": "learned_mac", "mac": mac, "vlan": row.get("vlan"),
                      "vendor": row.get("vendor"), "classification": row.get("classification")})
        edges.append({"from": "port:" + number, "to": node_id,
                      "relation": "mac_learned", "confidence": "observed",
                      "note": "A MAC foi aprendida nesta porta; não confirma conexão física direta."})
    return {"nodes": nodes, "edges": edges, "method": "fdb",
            "disclaimer": "Conexões físicas entre equipamentos intermediários não são confirmadas pela tabela MAC."}
