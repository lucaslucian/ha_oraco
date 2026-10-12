class HaOracoPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.tab = "overview";
    this.macFilter = "";
    this.data = null;
    this.lastFetch = 0;
    this.busy = false;
    this.samples = {};
  }
  set hass(value) {
    this._hass = value;
    if (!this.data || Date.now() - this.lastFetch > 25000) this.refresh();
  }
  connectedCallback() { this.render(); this.refresh(); }
  async refresh() {
    if (!this._hass || this.busy) return;
    this.busy = true;
    this.lastFetch = Date.now();
    try {
      this.data = await this._hass.connection.sendMessagePromise({type:"ha_oraco/dashboard"});
      for(const sw of this.data.switches || []) {
        const ports = Object.values(sw.ports || {});
        const rx = ports.reduce((sum,p)=>sum+(Number(p.rx_bps)||0),0);
        const tx = ports.reduce((sum,p)=>sum+(Number(p.tx_bps)||0),0);
        this.samples[sw.id] ||= [];
        this.samples[sw.id].push({rx,tx});
        if(this.samples[sw.id].length>120) this.samples[sw.id].shift();
      }
      this.error = null;
    } catch (err) { this.error = String(err); }
    finally { this.busy = false; this.render(); }
  }

  sfpLabel(key) {
    const names={temperature_c:"Temperatura",voltage_v:"Tensão",current_ma:"Corrente do laser",
      rx_dbm:"Potência recebida (RX)",tx_dbm:"Potência transmitida (TX)",
      vendor:"Fabricante",vendorname:"Fabricante",vendor_name:"Fabricante",
      part_number:"Modelo",partnumber:"Modelo",serial_number:"Número de série",
      serialnumber:"Número de série",wavelength_nm:"Comprimento de onda",
      wavelength:"Comprimento de onda",connector:"Conector",revision:"Revisão",
      rxpower:"RX bruto",txpower:"TX bruto",temp:"Temperatura bruta",
      voltage:"Tensão bruta",current:"Corrente bruta",distance:"Alcance"};
    return names[key]||key.replace(/_/g," ").replace(/^./,c=>c.toUpperCase());
  }
  sfpValue(key,value) {
    if(value===null||value===undefined||value==="")return "Indisponível";
    const units={temperature_c:[" °C",1],voltage_v:[" V",2],current_ma:[" mA",2],
      rx_dbm:[" dBm",2],tx_dbm:[" dBm",2],wavelength_nm:[" nm",0]};
    if(units[key]&&Number.isFinite(Number(value)))return Number(value).toLocaleString("pt-BR",
      {minimumFractionDigits:units[key][1],maximumFractionDigits:units[key][1]})+units[key][0];
    return this.escape(value);
  }
  renderSfp(sw,compact=false) {
    const raw=sw.sfp?.sfp||{};
    if(!Object.keys(raw).length)return '<p class="empty">Nenhuma informação óptica disponível.</p>';
    const readings=["rx_dbm","tx_dbm","temperature_c","voltage_v","current_ma"];
    const fields=readings.slice(0,compact?4:5).map(k=>'<div class="optical-item"><small>'
      +this.escape(this.sfpLabel(k))+'</small><strong>'+this.escape(this.sfpValue(k,raw[k]))+'</strong></div>').join("");
    const extra=compact?"":Object.entries(raw)
      .filter(([k])=>!readings.includes(k)&&!["temp","voltage","current","rxpower","txpower"].includes(k))
      .map(([k,v])=>'<div class="detail-item"><small>'+this.escape(this.sfpLabel(k))
      +'</small><strong>'+this.escape(v)+'</strong></div>').join("");
    return '<div class="optical-grid">'+fields+'</div>'+(extra?'<h4>Identificação do transceptor</h4><div class="detail-grid">'+extra+'</div>':"");
  }
  portFace(ports) {
    if(!ports.length)return '<p class="empty">Nenhuma interface identificada.</p>';
    return '<div class="switch-face"><div class="face-title"><span class="face-led"></span> INTERFACES MONITORADAS <span>'
      +ports.length+' PORTAS</span></div><div class="jack-grid">'
      +[...ports].sort((a,b)=>Number(a.port)-Number(b.port)).map(p=>
        '<div class="jack-port '+(p.up?"linked":"")+'" title="Porta '+this.escape(p.port)+'">'
        +'<b>'+this.escape(p.port)+'</b><div class="rj45"><div class="rj45-notch"></div></div>'
        +'<i class="jack-led"></i><small>'+this.escape(p.speed||"—")+'</small></div>').join("")
      +'</div><div class="face-legend"><span>● Verde: conectada</span><span>● Cinza: desconectada</span>'
      +'<span>Representação lógica; disposição física depende do modelo</span></div></div>';
  }
  trafficChart(id) {
    const samples=this.samples[id]||[];
    if(samples.length<2)return '<p class="empty">Aguardando duas amostras para iniciar o gráfico.</p>';
    const peak=Math.max(1,...samples.flatMap(v=>[v.rx,v.tx]));
    const points=key=>samples.map((v,i)=>((i*740)/Math.max(1,samples.length-1)+30).toFixed(1)
      +','+(159-v[key]/peak*134).toFixed(1)).join(' ');
    const grid=[26,70,115,159].map(y=>'<line x1="30" x2="770" y1="'+y+'" y2="'+y+'" stroke="currentColor" opacity=".12" stroke-dasharray="4 5"/>').join("");
    return '<svg class="traffic-chart" viewBox="0 0 800 185" role="img" aria-label="Tráfego RX e TX">'
      +grid+'<polyline points="'+points("rx")+'" fill="none" stroke="#29ade3" stroke-width="2.7" stroke-linejoin="round"/>'
      +'<polyline points="'+points("tx")+'" fill="none" stroke="#49bf87" stroke-width="2.7" stroke-linejoin="round"/></svg>'
      +'<div class="chart-legend"><span>● RX — azul</span><span>● TX — verde</span><span>'
      +samples.length+' amostras desta sessão</span></div>';
  }
  topologyMap(sw) {
    const ports=Object.values(sw.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
    if(!ports.length) return '<p class="empty">Sem interfaces identificadas.</p>';
    const nodes=sw.topology?.nodes||[];
    const edges=sw.topology?.edges||[];
    const width=980, lane=90, top=90, footer=45;
    const maxMac=15;
    const rows=ports.map(p=>{
      const ids=edges.filter(e=>e.from==="port:"+p.port && e.relation==="mac_learned").map(e=>e.to);
      return {port:p,devices:ids.map(id=>nodes.find(n=>n.id===id)).filter(Boolean),hidden:Math.max(0,ids.length-maxMac)};
    });
    const height=top+rows.length*lane+footer;
    const esc=v=>this.escape(v);
    const switchBox='<rect x="12" y="15" width="255" height="52" rx="12" fill="#172d44" stroke="#3b99b4"/>'
      +'<text x="29" y="45" fill="#eaf5ff" font-size="17" font-weight="600">Switch monitorado</text>';
    const body=rows.map((r,i)=>{
      const y=top+i*lane;
      const active=!!r.port.up, color=active?"#3cbc87":"#7d8993";
      const endpoint=380;
      const links=r.devices.slice(0,maxMac);
      const deviceText=links.length?links.map(n=>esc(n.label||n.mac)).join(" · "):"Nenhum MAC aprendido";
      const summary=links.length>3?deviceText.slice(0,90)+"…":deviceText;
      return '<path d="M140 67 V'+(y+19)+' H'+endpoint+'" fill="none" stroke="#47728c" stroke-width="1.7" opacity=".65"/>'
        +'<rect x="300" y="'+y+'" width="165" height="44" rx="9" fill="#182b3b" stroke="'+color+'" stroke-width="1.2"/>'
        +'<circle cx="317" cy="'+(y+22)+'" r="5" fill="'+color+'"/>'
        +'<text x="332" y="'+(y+18)+'" fill="#eaf5ff" font-size="13">Porta '+esc(r.port.port)+'</text>'
        +'<text x="332" y="'+(y+34)+'" fill="#9aafbf" font-size="10">'+esc(r.port.speed||"—")+'</text>'
        +'<path d="M465 '+(y+22)+' H535" fill="none" stroke="'+color+'" stroke-width="1.7" opacity=".8"/>'
        +'<rect x="535" y="'+y+'" width="410" height="44" rx="9" fill="#122739" stroke="#466175"/>'
        +'<text x="550" y="'+(y+18)+'" fill="#eaf5ff" font-size="12">'+esc(links.length+(r.hidden||0))+' MACs observados</text>'
        +'<text x="550" y="'+(y+34)+'" fill="#a3b4c1" font-size="10">'+esc(summary)+'</text>';
    }).join("");
    const diagram='<div class="topology-scroll"><svg class="topology-svg" viewBox="0 0 '+width+' '+height+'" role="img" aria-label="Topologia lógica do switch, portas e MACs">'
      +switchBox+body+'</svg></div>';
    return diagram+'<p class="topology-disclaimer">As conexões indicam MACs aprendidos em cada porta e não confirmam ligações físicas diretas. A exibição resume até 15 MACs por porta.</p>';
  }
  escape(v) {
    return String(v ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  render() {
    if (!this.shadowRoot) return;
    const switches = this.data?.switches || [];
    const tabs = [["overview","Visão geral"],["ports","Portas"],["sfp","SFP+"],["mac","Dispositivos"],["vlan","VLANs"],["protection","Proteções"],["topology","Mapa de rede"],["system","Sistema"]];
    let body = this.error ? '<section class="card">Não foi possível consultar os dados. '+this.escape(this.error)+'</section>' : "";
    if (!switches.length && !this.error) body = '<section class="card">Nenhum switch configurado ou aguardando dados.</section>';
    for (const sw of switches) {
      const ps = Object.values(sw.ports || {});
      const online = ps.filter(p=>p.up).length;
      const rate = side => ps.reduce((sum,p)=>sum + (Number(p[side+"_bps"]) || 0),0);
      const fmt = n => n >= 1e9 ? (n/1e9).toFixed(2)+" Gb/s" : n>=1e6 ? (n/1e6).toFixed(1)+" Mb/s" : n>=1e3 ? (n/1e3).toFixed(1)+" kb/s" : n.toFixed(0)+" b/s";
      const peak=number=>sw.peaks?.ports?.[number]||{};
      const row = (p) => '<tr><td>Porta '+this.escape(p.port)+'</td><td><span class="dot '+(p.up?"ok":"")+'"></span>'+(p.up?"Ativa":"Inativa")+'</td><td>'+this.escape(p.speed)+'</td><td>'+fmt(Number(p.rx_bps)||0)+'</td><td>'+fmt(Number(p.tx_bps)||0)+'</td><td>'+fmt(peak(p.port).rx_bps||0)+'</td><td>'+fmt(peak(p.port).tx_bps||0)+'</td></tr>';
      body += '<div class="heading"><h2>'+this.escape(sw.name)+'</h2><span>'+this.escape(sw.host)+'</span></div>';
      if (this.tab === "overview") {
        body += '<div class="stats"><section class="card metric"><small>Portas ativas</small><strong>'+online+' / '+ps.length+'</strong></section><section class="card metric"><small>Tráfego RX</small><strong>'+fmt(rate("rx"))+'</strong></section><section class="card metric"><small>Tráfego TX</small><strong>'+fmt(rate("tx"))+'</strong></section><section class="card metric"><small>Firmware</small><strong class="small">'+this.escape(sw.device?.firmware)+'</strong></section></div>';
        body += '<div class="peak-strip"><span>Picos desde o início da integração</span><strong>RX '+fmt(sw.peaks?.total?.rx_bps||0)+'</strong><strong>TX '+fmt(sw.peaks?.total?.tx_bps||0)+'</strong></div>';
        body += '<section class="card"><h3>Tráfego ao vivo</h3>'+this.trafficChart(sw.id)+'</section>';
        body += '<section class="card"><h3>Visão das interfaces</h3><p class="section-subtitle">Estado das portas e velocidade negociada</p>'+this.portFace(ps)+'</section>';
        body += '<div class="columns"><section class="card"><h3>Portas e tráfego</h3>'+table(ps.slice(0,12))+'</section><section class="card"><h3>Diagnóstico SFP+</h3>'+this.renderSfp(sw,true)+'<h3 class="spaced">Inventário MAC</h3><p>'+this.escape(sw.mac?.mac_current ?? "—")+' MACs atuais · '+this.escape(sw.mac?.mac_known ?? "—")+' conhecidos</p></section></div>';
      } else if(this.tab === "ports") body += '<section class="card"><h3>Visão das interfaces</h3>'+this.portFace(ps)+'</section><section class="card"><h3>Portas e utilização</h3>'+table(ps)+'</section>';
      else if(this.tab === "sfp") body += '<section class="card"><h3>Transceptor óptico</h3><p class="section-subtitle">Medições e dados de identificação disponíveis no firmware</p>'+this.renderSfp(sw)+'</section>';
      else if(this.tab === "mac") body += '<section class="card"><h3>MACs observados · '+this.escape(sw.mac?.mac_current ?? "—")+'</h3><p>Mostrando até 25 MACs atuais; filtros aplicados localmente. Histórico preservado na integração.</p><input id="mac-filter" type="search" placeholder="Pesquisar MAC, porta, VLAN ou fabricante" value="'+this.escape(this.macFilter)+'" aria-label="Filtrar endereços MAC"><div class="scroll"><table><thead><tr><th>MAC</th><th>Porta</th><th>VLAN</th><th>Fabricante / classificação</th></tr></thead><tbody>'+(sw.mac?.mac_entries||[]).filter(e=>JSON.stringify(e).toLowerCase().includes(this.macFilter.toLowerCase())).map(e=>'<tr><td>'+this.escape(e.mac)+'</td><td>'+this.escape(e.port)+'</td><td>'+this.escape(e.vlan)+'</td><td>'+this.escape(e.vendor || e.classification)+'</td></tr>').join("")+'</tbody></table></div></section>';
      else if(this.tab === "topology") body += '<section class="card"><h3>Mapa lógico da rede</h3>'+this.topologyMap(sw)+'</section>';
      else if(this.tab === "protection") {
        const net=sw.network||{};
        const iso=Object.values(net.isolation?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const stp=Object.values(net.stp_ports?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const storm=Object.values(net.storm_control?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const status=rows=>rows.length?'':'<p class="empty">Sem dados disponíveis para este recurso.</p>';
        const tbl=(cols,rows)=>'<div class="scroll"><table><thead><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';
        body+='<section class="card"><h3>Isolamento de portas</h3><p class="section-subtitle">Listas apresentadas pelo firmware; o sentido das restrições ainda requer validação.</p>'+status(iso)
          +(iso.length?tbl(['Porta','Lista informada','Portas listadas'],iso.map(p=>'<tr><td>Porta '+this.escape(p.port)+'</td><td>'+this.escape(p.raw_list)+'</td><td>'+this.escape(p.listed_ports?.join(', '))+'</td></tr>')):'')+'</section>';
        body+='<section class="card"><h3>Spanning Tree — portas</h3><p class="section-subtitle">Estado, função, custo e parâmetros efetivos de STP.</p>'+status(stp)
          +(stp.length?tbl(['Porta','Estado','Função','Custo configurado','Custo efetivo','Prioridade','P2P efetivo','Edge efetivo'],stp.map(p=>
            '<tr><td>Porta '+this.escape(p.port)+'</td><td>'+this.escape(p.state)+'</td><td>'+this.escape(p.role)+'</td><td>'+this.escape(p.path_cost_config)+'</td><td>'+this.escape(p.path_cost_actual)+'</td><td>'+this.escape(p.priority)+'</td><td>'+this.escape(p.p2p_actual)+'</td><td>'+this.escape(p.edge_actual)+'</td></tr>')):'')+'</section>';
        const stormValue=v=>v===null||v===undefined?'Desativado':this.escape(v)+' kbit/s';
        body+='<section class="card"><h3>Controle de tempestades</h3><p class="section-subtitle">Limites configurados por interface. Desativado não significa tráfego zero.</p>'+status(storm)
          +(storm.length?tbl(['Porta','Broadcast','Multicast conhecido','Multicast desconhecido','Unicast desconhecido'],storm.map(p=>
            '<tr><td>Porta '+this.escape(p.port)+'</td><td>'+stormValue(p.broadcast_kbps)+'</td><td>'+stormValue(p.known_multicast_kbps)+'</td><td>'+stormValue(p.unknown_multicast_kbps)+'</td><td>'+stormValue(p.unknown_unicast_kbps)+'</td></tr>')):'')+'</section>';
      }
      else if(this.tab === "system") body += '<section class="card"><h3>Informações do equipamento</h3>'+Object.entries(sw.device||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v)+'</b></div>').join("")+'<h3>Saúde dos endpoints</h3>'+Object.entries(sw.diagnostics?.endpoints||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v.status)+'</b></div>').join("")+'</section>';
      else if(this.tab === "vlan") {
        const vlans=sw.network?.vlan_ports?.ports||{};
        const vlanRows=Object.values(vlans).sort((a,b)=>Number(a.port)-Number(b.port));
        const fmt=items=>Array.isArray(items)&&items.length?items.map(v=>'<span class="vlan-pill">'+this.escape(v)+'</span>').join(" "):'<span class="muted">—</span>';
        body += '<section class="card"><h3>Configuração de VLANs por porta</h3><p class="section-subtitle">Leitura da tabela de estado do switch; nenhuma configuração é alterada.</p>'
          +(vlanRows.length?'<div class="scroll"><table class="vlan-table"><thead><tr><th>Porta</th><th>Modo</th><th>Access</th><th>Nativa / PVID*</th><th>Tagged</th><th>Untagged</th><th>VLANs permitidas</th></tr></thead><tbody>'
            +vlanRows.map(p=>'<tr><td><strong>Porta '+this.escape(p.port)+'</strong></td><td><span class="mode-pill">'+this.escape((p.mode||"—").toUpperCase())+'</span>'
              +(p.accepted_frames?'<small class="mode-detail">'+this.escape(p.accepted_frames)+'</small>':"")+'</td><td>'+this.escape(p.access_vlan??"—")+'</td><td>'+this.escape(p.native_vlan??"—")+'</td><td>'+fmt(p.tagged_vlans)+'</td><td>'+fmt(p.untagged_vlans)+'</td><td>'+fmt(p.allowed_vlans)+'</td></tr>').join("")+'</tbody></table></div>'
            :'<p class="empty">Nenhuma tabela de VLANs disponível ainda.</p>')
          +'<p class="footnote">* A interface do firmware identifica a coluna como Native VLAN. Não assumimos que represente todas as configurações de PVID ou isolamento.</p></section>';
      }
      else body += '<section class="card"><h3>'+this.escape(tabs.find(t=>t[0]===this.tab)?.[1])+'</h3><p>Esta área será preenchida automaticamente quando os dados forem disponibilizados pela integração e validados no firmware. Nenhum dado fictício é exibido.</p></section>';
      function table(items) { return '<div class="scroll"><table><thead><tr><th>Interface</th><th>Link</th><th>Velocidade</th><th>RX</th><th>TX</th><th>Pico RX</th><th>Pico TX</th></tr></thead><tbody>'+items.map(row).join("")+'</tbody></table></div>'; }
    }
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); font-family:Roboto,"Arial",sans-serif; }
      *{box-sizing:border-box} main{max-width:1480px;margin:auto;padding:24px;} header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:22px}
      .brand{display:flex;align-items:center;gap:12px}.brand img{width:38px;height:38px;object-fit:contain} h1{font-size:24px;font-weight:500;margin:0}h2{font-size:19px;font-weight:500;margin:0}h3{font-size:15px;font-weight:500;margin:0 0 18px}
      nav{display:flex;gap:6px;overflow-x:auto;border-bottom:1px solid var(--divider-color);margin-bottom:24px}
      button{font:inherit;cursor:pointer;background:transparent;color:var(--secondary-text-color);border:0;border-bottom:2px solid transparent;padding:13px 15px;white-space:nowrap}
      button.selected{color:var(--primary-color);border-color:var(--primary-color)}button:hover{color:var(--primary-text-color)}
      button.refresh{border:1px solid var(--divider-color);border-radius:8px;padding:9px 16px}
      .heading{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:24px 0 14px}.heading span,small,p{color:var(--secondary-text-color)}
      .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:20px;margin-bottom:16px}
      .metric small{display:block;font-size:13px;margin-bottom:10px}.metric strong{font-size:25px;font-weight:500}.metric strong.small{font-size:15px}
      .columns{display:grid;grid-template-columns:2fr 1fr;gap:16px}.port-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(82px,1fr));gap:10px}.port{background:var(--secondary-background-color);border:1px solid var(--divider-color);padding:12px;border-radius:8px;text-align:center}
      .port.active{border-color:var(--success-color,#4caf50)}.port b{display:block;font-size:16px}.port span{font-size:11px;color:var(--secondary-text-color)}.scroll{overflow:auto}
      .traffic-chart{display:block;width:100%;height:auto;max-height:200px} table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:12px 10px;border-bottom:1px solid var(--divider-color);white-space:nowrap}th{font-weight:500;color:var(--secondary-text-color)}
      .dot{display:inline-block;width:8px;height:8px;background:var(--disabled-text-color);border-radius:50%;margin-right:8px}.dot.ok{background:var(--success-color,#4caf50)}
      input[type=search]{width:100%;padding:12px 14px;border:1px solid var(--divider-color);border-radius:8px;background:var(--secondary-background-color);color:var(--primary-text-color);margin-bottom:12px} .kv{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--divider-color);gap:15px}.kv span{color:var(--secondary-text-color)}

      .vlan-table td{vertical-align:middle}.vlan-pill{display:inline-block;padding:3px 7px;margin:2px;border-radius:6px;background:var(--secondary-background-color);border:1px solid var(--divider-color);font-size:11px}.mode-pill{display:inline-block;border-radius:7px;padding:5px 8px;background:var(--secondary-background-color);border:1px solid var(--divider-color);font-size:10px;font-weight:650}.mode-detail{display:block;margin-top:5px;color:var(--secondary-text-color)}.muted{color:var(--secondary-text-color)}
      .peak-strip{display:flex;flex-wrap:wrap;gap:20px;align-items:center;padding:13px 18px;margin:-2px 0 15px;background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;font-size:12px}.peak-strip span{color:var(--secondary-text-color)}.peak-strip strong{font-size:13px}
      .topology-scroll{overflow:auto;max-height:700px;border-radius:12px;background:#0b1a29;padding:10px}.topology-svg{display:block;width:100%;min-width:800px;height:auto;max-height:none}.topology-disclaimer{font-size:12px;color:var(--secondary-text-color)}
      .section-subtitle{font-size:12px;color:var(--secondary-text-color);margin:-8px 0 18px}
      .switch-face{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:19px}
      .face-title{display:flex;gap:10px;align-items:center;font-size:10px;letter-spacing:1px;color:var(--secondary-text-color);font-weight:600;margin-bottom:18px}
      .face-title>span:last-child{margin-left:auto}.face-led{width:8px;height:8px;border-radius:50%;background:#49bf87}
      .jack-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(76px,1fr));gap:11px}
      .jack-port{min-height:108px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px}
      .jack-port>b{font-size:12px}.jack-port>small{font-size:10px;color:var(--secondary-text-color)}
      .rj45{height:29px;width:38px;border:2px solid #607080;border-radius:5px;background:#101923;display:grid;place-items:center}
      .rj45-notch{width:22px;height:18px;border:2px solid #607080;border-top:0}
      .jack-port.linked .rj45{border-color:#49bf87}.jack-led{width:7px;height:7px;border-radius:50%;background:var(--disabled-text-color)}
      .jack-port.linked .jack-led{background:#49bf87;box-shadow:0 0 0 3px rgba(73,191,135,.13)}
      .face-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:16px;font-size:11px;color:var(--secondary-text-color)}
      .optical-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;margin:17px 0}
      .optical-item,.detail-item{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:10px;padding:14px;min-width:0}
      .optical-item small,.detail-item small{display:block;color:var(--secondary-text-color);font-size:11px;margin-bottom:10px}
      .optical-item strong{font-size:17px;font-weight:600;overflow-wrap:anywhere}.detail-item strong{font-size:13px;overflow-wrap:anywhere}
      .detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.spaced{margin-top:22px}
      .chart-legend{display:flex;gap:17px;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color);margin:3px 0 0 22px}
      .traffic-chart{max-height:190px}.card{border-radius:14px}.metric{min-width:0}.metric strong{overflow-wrap:anywhere}
      @media(max-width:950px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.columns{grid-template-columns:1fr}}@media(max-width:500px){main{padding:14px}.stats{gap:8px}.card{padding:14px}.metric strong{font-size:20px}}
    </style><main><header><h1 class="brand"><img src="/ha_oraco_static/brand/icon.svg" alt="" aria-hidden="true"/> HoraInfo</h1><button class="refresh" id="refresh">Atualizar</button></header>
    <nav>${tabs.map(([id,label])=>'<button data-tab="'+id+'" class="'+(id===this.tab?"selected":"")+'">'+label+'</button>').join("")}</nav>
    ${body}</main>`;
    this.shadowRoot.querySelectorAll("[data-tab]").forEach(el => el.addEventListener("click", () => {this.tab=el.dataset.tab;this.render()}));
    this.shadowRoot.getElementById("refresh")?.addEventListener("click",()=>this.refresh());
    this.shadowRoot.getElementById("mac-filter")?.addEventListener("change",ev=>{this.macFilter=ev.target.value;this.render()});
  }
}
customElements.define("ha-oraco-panel",HaOracoPanel);
