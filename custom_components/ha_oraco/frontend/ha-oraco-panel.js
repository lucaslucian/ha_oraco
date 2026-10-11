class HaOracoPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.tab = "overview";
    this.data = null;
    this.lastFetch = 0;
    this.busy = false;
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
      this.error = null;
    } catch (err) { this.error = String(err); }
    finally { this.busy = false; this.render(); }
  }
  escape(v) {
    return String(v ?? "—").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  render() {
    if (!this.shadowRoot) return;
    const switches = this.data?.switches || [];
    const tabs = [["overview","Visão geral"],["ports","Portas"],["sfp","SFP+"],["mac","Dispositivos"],["vlan","VLANs"],["topology","Mapa de rede"],["system","Sistema"]];
    let body = this.error ? '<section class="card">Não foi possível consultar os dados. '+this.escape(this.error)+'</section>' : "";
    if (!switches.length && !this.error) body = '<section class="card">Nenhum switch configurado ou aguardando dados.</section>';
    for (const sw of switches) {
      const ps = Object.values(sw.ports || {});
      const online = ps.filter(p=>p.up).length;
      const rate = side => ps.reduce((sum,p)=>sum + (Number(p[side+"_bps"]) || 0),0);
      const fmt = n => n >= 1e9 ? (n/1e9).toFixed(2)+" Gb/s" : n>=1e6 ? (n/1e6).toFixed(1)+" Mb/s" : n>=1e3 ? (n/1e3).toFixed(1)+" kb/s" : n.toFixed(0)+" b/s";
      const row = (p) => '<tr><td>Porta '+this.escape(p.port)+'</td><td><span class="dot '+(p.up?"ok":"")+'"></span>'+(p.up?"Ativa":"Inativa")+'</td><td>'+this.escape(p.speed)+'</td><td>'+fmt(Number(p.rx_bps)||0)+'</td><td>'+fmt(Number(p.tx_bps)||0)+'</td></tr>';
      body += '<div class="heading"><h2>'+this.escape(sw.name)+'</h2><span>'+this.escape(sw.host)+'</span></div>';
      if (this.tab === "overview") {
        body += '<div class="stats"><section class="card metric"><small>Portas ativas</small><strong>'+online+' / '+ps.length+'</strong></section><section class="card metric"><small>Tráfego RX</small><strong>'+fmt(rate("rx"))+'</strong></section><section class="card metric"><small>Tráfego TX</small><strong>'+fmt(rate("tx"))+'</strong></section><section class="card metric"><small>Firmware</small><strong class="small">'+this.escape(sw.device?.firmware)+'</strong></section></div>';
        body += '<section class="card"><h3>Interfaces</h3><div class="port-grid">'+ps.map(p=>'<div class="port '+(p.up?"active":"")+'"><b>'+this.escape(p.port)+'</b><span>'+this.escape(p.speed)+'</span></div>').join("")+'</div></section>';
        body += '<div class="columns"><section class="card"><h3>Portas e tráfego</h3>'+table(ps.slice(0,12))+'</section><section class="card"><h3>Diagnóstico SFP+</h3><div class="kv"><span>Temperatura</span><b>'+this.escape(sw.sfp?.sfp?.temperature_c)+' °C</b></div><div class="kv"><span>RX óptico</span><b>'+this.escape(sw.sfp?.sfp?.rx_dbm)+' dBm</b></div><div class="kv"><span>TX óptico</span><b>'+this.escape(sw.sfp?.sfp?.tx_dbm)+' dBm</b></div><h3>Inventário MAC</h3><p>'+this.escape(sw.mac?.mac_current ?? "—")+' MACs atuais · '+this.escape(sw.mac?.mac_known ?? "—")+' conhecidos</p></section></div>';
      } else if(this.tab === "ports") body += '<section class="card"><h3>Portas e utilização</h3>'+table(ps)+'</section>';
      else if(this.tab === "sfp") body += '<section class="card"><h3>Diagnóstico óptico</h3>'+Object.entries(sw.sfp?.sfp||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v)+'</b></div>').join("")+'</section>';
      else if(this.tab === "mac") body += '<section class="card"><h3>MACs observados · '+this.escape(sw.mac?.mac_current ?? "—")+'</h3><p>Mostrando no máximo 25 registros recentes. Histórico preservado na integração.</p><div class="scroll"><table><thead><tr><th>MAC</th><th>Porta</th><th>VLAN</th><th>Classificação</th></tr></thead><tbody>'+(sw.mac?.mac_entries||[]).map(e=>'<tr><td>'+this.escape(e.mac)+'</td><td>'+this.escape(e.port)+'</td><td>'+this.escape(e.vlan)+'</td><td>'+this.escape(e.classification)+'</td></tr>').join("")+'</tbody></table></div></section>';
      else if(this.tab === "topology") body += '<section class="card"><h3>Mapa lógico por porta</h3><p>Relações baseadas na tabela MAC aprendida. Dispositivos atrás de APs ou switches não gerenciados podem aparecer conectados à mesma porta, sem confirmar ligação física direta.</p>'+ps.map(p=>'<div class="kv"><span>Porta '+this.escape(p.port)+'</span><b>'+this.escape((sw.topology?.edges||[]).filter(e=>e.from==="port:"+p.port).length)+' MAC(s) observado(s)</b></div>').join("")+'</section>';
      else if(this.tab === "system") body += '<section class="card"><h3>Informações do equipamento</h3>'+Object.entries(sw.device||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v)+'</b></div>').join("")+'</section>';
      else body += '<section class="card"><h3>'+this.escape(tabs.find(t=>t[0]===this.tab)?.[1])+'</h3><p>Esta área será preenchida automaticamente quando os dados forem disponibilizados pela integração e validados no firmware. Nenhum dado fictício é exibido.</p></section>';
      function table(items) { return '<div class="scroll"><table><thead><tr><th>Interface</th><th>Link</th><th>Velocidade</th><th>RX</th><th>TX</th></tr></thead><tbody>'+items.map(row).join("")+'</tbody></table></div>'; }
    }
    this.shadowRoot.innerHTML = `<style>
      :host { display:block; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); font-family:Roboto,"Arial",sans-serif; }
      *{box-sizing:border-box} main{max-width:1480px;margin:auto;padding:24px;} header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:22px}
      h1{font-size:24px;font-weight:500;margin:0}h2{font-size:19px;font-weight:500;margin:0}h3{font-size:15px;font-weight:500;margin:0 0 18px}
      nav{display:flex;gap:6px;overflow-x:auto;border-bottom:1px solid var(--divider-color);margin-bottom:24px}
      button{font:inherit;cursor:pointer;background:transparent;color:var(--secondary-text-color);border:0;border-bottom:2px solid transparent;padding:13px 15px;white-space:nowrap}
      button.selected{color:var(--primary-color);border-color:var(--primary-color)}button:hover{color:var(--primary-text-color)}
      button.refresh{border:1px solid var(--divider-color);border-radius:8px;padding:9px 16px}
      .heading{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:24px 0 14px}.heading span,small,p{color:var(--secondary-text-color)}
      .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:20px;margin-bottom:16px}
      .metric small{display:block;font-size:13px;margin-bottom:10px}.metric strong{font-size:25px;font-weight:500}.metric strong.small{font-size:15px}
      .columns{display:grid;grid-template-columns:2fr 1fr;gap:16px}.port-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(82px,1fr));gap:10px}.port{background:var(--secondary-background-color);border:1px solid var(--divider-color);padding:12px;border-radius:8px;text-align:center}
      .port.active{border-color:var(--success-color,#4caf50)}.port b{display:block;font-size:16px}.port span{font-size:11px;color:var(--secondary-text-color)}.scroll{overflow:auto}
      table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:12px 10px;border-bottom:1px solid var(--divider-color);white-space:nowrap}th{font-weight:500;color:var(--secondary-text-color)}
      .dot{display:inline-block;width:8px;height:8px;background:var(--disabled-text-color);border-radius:50%;margin-right:8px}.dot.ok{background:var(--success-color,#4caf50)}
      .kv{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--divider-color);gap:15px}.kv span{color:var(--secondary-text-color)}
      @media(max-width:950px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.columns{grid-template-columns:1fr}}@media(max-width:500px){main{padding:14px}.stats{gap:8px}.card{padding:14px}.metric strong{font-size:20px}}
    </style><main><header><h1>HA Oraco</h1><button class="refresh" id="refresh">Atualizar</button></header>
    <nav>${tabs.map(([id,label])=>'<button data-tab="'+id+'" class="'+(id===this.tab?"selected":"")+'">'+label+'</button>').join("")}</nav>
    ${body}</main>`;
    this.shadowRoot.querySelectorAll("[data-tab]").forEach(el => el.addEventListener("click", () => {this.tab=el.dataset.tab;this.render()}));
    this.shadowRoot.getElementById("refresh")?.addEventListener("click",()=>this.refresh());
  }
}
customElements.define("ha-oraco-panel",HaOracoPanel);
