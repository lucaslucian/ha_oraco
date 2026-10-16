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
    this.selectedPort = {};
    this.chartHours = {};
    this.sfpTemperatureHours = {};
    this.sfpOpticalHours = {};
    this.historyViews = {};
    this.historyRequests = {};
    this.historyPanels = {};
    this.snapshotModal = null;
    this.snapshotDay = null;
    this.portModal = null;
    this.devicePortFilter = "all";
    this.deviceVlanFilter = "all";
    this.deviceVendorFilter = "all";
    this.macPages = {};
    this.ddmiState = {};
    this.endpointSelection = {};
  }
  set hass(value) {
    this._hass = value;
    if (!this.data || Date.now() - this.lastFetch > 25000) this.refresh();
  }
  connectedCallback() {
    this._modalKeydown = event => {
      if(event.key==="Escape"&&(this.snapshotModal||this.portModal)){
        this.snapshotModal=null;this.portModal=null;this.render();
      }
    };
    window.addEventListener("keydown",this._modalKeydown);
    this.render();this.refresh();
  }
  disconnectedCallback() {
    if(this._modalKeydown)window.removeEventListener("keydown",this._modalKeydown);
  }
  formatAuditDate(value,timeOnly=false) {
    const date=new Date(value);
    if(!Number.isFinite(date.getTime()))return "Data indisponível";
    return timeOnly?date.toLocaleTimeString("pt-BR"):date.toLocaleString("pt-BR");
  }
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
        this.samples[sw.id].push({rx,tx,timestamp:new Date().toISOString()});
        if(this.samples[sw.id].length>120) this.samples[sw.id].shift();
      }
      this.error = null;
    } catch (err) { this.error = this.readableError(err); }
    finally { this.busy = false; this.render(); this.loadCurrentCharts(true); this.loadSfpTemperature(); this.loadSfpOptics(); this.loadStorageStats(); }
  }

  async refreshDdmi(switchId) {
    if(!this._hass || this.ddmiState[switchId]?.loading)return;
    this.ddmiState[switchId]={loading:true};
    this.render();
    try {
      const result=await this._hass.connection.sendMessagePromise({
        type:"ha_oraco/ddmi_refresh",entry_id:switchId
      });
      this.ddmiState[switchId]=result&&typeof result==="object"?result:
        {status:"error",error:"Resposta inválida"};
      if(result?.status==="ok")await this.refresh();
    } catch(error) {
      this.ddmiState[switchId]={status:"error",error:this.readableError(error)};
    }
    this.render();
  }
  macSettings(sw) {
    const defaults={query:"",port:"all",vlan:"all",vendor:"all",page_size:50,height:440};
    return {...defaults,...(sw.preferences?.options?.mac_view||{})};
  }
  endpointDocs(sw) {
    const catalog=sw.endpoint_catalog||[];
    const selected=this.endpointSelection[sw.id]||catalog[0]?.key;
    const item=catalog.find(x=>x.key===selected)||catalog[0];
    if(!item)return '<section class="card"><p class="muted">Catálogo indisponível nesta versão.</p></section>';
    const endpoint=sw.diagnostics?.endpoints?.[item.key]||{};
    const payload=item.key==="sfp"?sw.sfp?.sfp:item.key==="ports"?sw.ports:
      item.key==="traffic"?sw.ports:item.key==="mac"?sw.mac:sw.network?.[item.key];
    const fields=payload&&typeof payload==="object"?Object.keys(payload):[];
    const status=endpoint.status||((item.key==="ports"||item.key==="traffic")?"Coleta principal":"Ainda não consultado");
    return '<section class="card"><h3>Explorador de endpoints · somente leitura</h3>'+
      '<p class="section-subtitle">Documentação dos caminhos CGI aprovados. Não executa comandos no switch; os exemplos vêm do último cache recebido pelo Home Assistant.</p>'+
      '<label class="endpoint-picker">Recurso<select data-endpoint-select="'+this.escape(sw.id)+'" aria-label="Escolher endpoint">'+
      catalog.map(entry=>'<option value="'+this.escape(entry.key)+'" '+(item.key===entry.key?'selected':'')+'>'+this.escape(entry.description)+'</option>').join('')+'</select></label>'+
      '<div class="detail-grid"><div class="detail-item"><small>Método</small><strong>GET (leitura)</strong></div>'+
      '<div class="detail-item"><small>Caminho</small><strong>'+this.escape(item.path)+'</strong></div>'+
      '<div class="detail-item"><small>Periodicidade planejada</small><strong>'+this.escape(item.interval_seconds)+' s</strong></div>'+
      '<div class="detail-item"><small>Diagnóstico</small><strong>'+this.escape(status)+'</strong></div></div>'+
      '<p class="muted">Último sucesso: '+this.escape(this.formatAuditDate(endpoint.last_success||sw.diagnostics?.last_success))+
      (endpoint.error?' · Erro: '+this.escape(endpoint.error):'')+'</p>'+
      '<h4>Campos identificados</h4><p class="muted">'+(fields.length?fields.map(x=>this.escape(x)).join(" · "):"Sem estrutura validada no cache atual")+'</p>'+
      '<details><summary>Visualizar dados atuais (cache local)</summary><pre class="endpoint-json">'+
      this.escape(payload===undefined||payload===null?"Nenhum dado disponível":JSON.stringify(payload,null,2).slice(0,12000))+
      '</pre></details><p class="footnote">Saídas exibidas apenas ao administrador; não incluem HTML bruto, cookies ou senhas. Dados ausentes não comprovam que o equipamento suporta o recurso.</p></section>';
  }
  networkServices(sw) {
    const dhcp=sw.network?.dhcp,igmp=sw.network?.igmp;
    const ports=Object.keys(sw.ports||{}).sort((a,b)=>Number(a)-Number(b));
    const groups=Array.isArray(igmp?.groups)?igmp.groups:[];
    return '<section class="card"><h3>DHCP snooping e IGMP por porta</h3>'+
      '<p class="section-subtitle">Leitura dos caminhos CGI conhecidos. Estados por porta só aparecem quando confirmados em tabelas com cabeçalhos explícitos.</p>'+
      '<div class="inventory-stats"><div><small>DHCP snooping</small><strong>'+(!dhcp?"Indisponível":dhcp.enabled?"Ativado":"Desativado")+'</strong></div>'+
      '<div><small>IGMP snooping</small><strong>'+(!igmp?"Indisponível":igmp.enabled?"Ativado":"Desativado")+'</strong></div>'+
      '<div><small>Grupos IGMP identificados</small><strong>'+groups.length+'</strong></div></div>'+
      '<div class="scroll"><table><thead><tr><th>Porta</th><th>Confiabilidade DHCP</th><th>Grupos IGMP</th></tr></thead><tbody>'+
      ports.map(port=>{
        const trusted=dhcp?.per_port?.[port]?.trusted;
        const membership=igmp?.per_port?.[port]||[];
        return '<tr><td>Porta '+this.escape(port)+'</td><td>'+(!dhcp?.trust_status_available||trusted===undefined?"Não informado pelo firmware":trusted?"Confiável":"Não confiável")+'</td><td>'+
          (membership.length?membership.map(g=>this.escape(g.group)+' (VLAN '+this.escape(g.vlan)+')').join(" · "):"Nenhum grupo identificado")+
          '</td></tr>';
      }).join('')+'</tbody></table></div>'+
      (groups.length?'<h4>Grupos encontrados</h4><div class="scroll"><table><thead><tr><th>Grupo/IP</th><th>VLAN</th><th>Portas informadas</th></tr></thead><tbody>'+
      groups.map(g=>'<tr><td>'+this.escape(g.ip)+'</td><td>'+this.escape(g.vlan)+'</td><td>'+this.escape(g.ports)+'</td></tr>').join('')+
      '</tbody></table></div>':'<p class="muted">Nenhuma associação IGMP confirmada. O firmware pode não fornecer esta tabela.</p>')+
      '<p class="footnote">Não interpreta formulários de configuração como prova de estado operacional e não modifica confiança de portas nem grupos multicast.</p></section>';
  }
  loadCurrentCharts(refresh=false) {
    if(!this._hass||!this.data||this.tab!=="history")return;
    for(const sw of this.data.switches||[]){
      const port=this.selectedPort[sw.id]||"__total__";
      if(!port)continue;
      const hours=this.chartHours[sw.id+"|"+port]||this.defaultRange(sw);
      const trafficKey=sw.id+"|traffic|"+port+"|"+hours+"|sfp";
      const dailyKey=sw.id+"|daily|"+port+"|24|sfp";
      if(refresh||!this.historyViews[trafficKey])this.fetchHistory(sw.id,"traffic",port,hours);
      if(!this.historyViews[dailyKey])this.fetchHistory(sw.id,"daily",port);
    }
  }
  loadSfpTemperature() {
    if(!this._hass||!this.data||this.tab!=="sfp")return;
    for(const sw of this.data.switches||[]){
      const hours=this.sfpTemperatureHours[sw.id]||24;
      const key=sw.id+"|sfp_temperature|__total__|"+hours+"|sfp";
      if(!this.historyViews[key])this.fetchHistory(sw.id,"sfp_temperature","__total__",hours);
    }
  }
  loadSfpOptics() {
    if(!this._hass||!this.data||this.tab!=="sfp")return;
    for(const sw of this.data.switches||[]){
      const hours=this.sfpOpticalHours[sw.id]||24;
      for(const metric of ["voltage_v","current_ma","rx_dbm","tx_dbm"]){
        const key=sw.id+"|sfp_optical|__total__|"+hours+"|"+metric;
        if(!this.historyViews[key])this.fetchHistory(sw.id,"sfp_optical","__total__",hours,metric);
      }
    }
  }
  sfpOpticalCharts(sw) {
    const hours=this.sfpOpticalHours[sw.id]||24;
    const options=[[1,"1 hora"],[6,"6 horas"],[12,"12 horas"],[24,"1 dia"],
                   [72,"3 dias"],[120,"5 dias"],[168,"7 dias"]];
    const select='<label>Período<select class="history-select" data-sfp-optical-hours="'+this.escape(sw.id)+'">'+
      options.map(([h,label])=>'<option value="'+h+'" '+(hours===h?'selected':'')+'>'+label+'</option>').join("")+'</select></label>';
    const charts=[
      ["voltage_v","Tensão do módulo","V"],
      ["current_ma","Corrente do laser","mA"],
      ["rx_dbm","Potência recebida (RX)","dBm"],
      ["tx_dbm","Potência transmitida (TX)","dBm"]
    ].map(([metric,title,unit])=>{
      const key=sw.id+"|sfp_optical|__total__|"+hours+"|"+metric;
      const record=this.historyViews[key];
      const format=v=>Number(v).toLocaleString("pt-BR",{minimumFractionDigits:2,maximumFractionDigits:2})+" "+unit;
      if(!record||record.loading)return '<div class="optical-history-tile"><h4>'+title+'</h4><p class="muted">Carregando medições…</p></div>';
      if(record.error)return '<div class="optical-history-tile"><h4>'+title+'</h4><p class="muted">'+this.escape(record.error)+'</p></div>';
      const samples=record.items||[];
      if(!samples.length)return '<div class="optical-history-tile"><h4>'+title+'</h4><p class="muted">Sem medições disponíveis neste período.</p></div>';
      const low=Number(record.min),high=Number(record.max);
      const pad=Math.max((high-low)*.12,unit==="dBm"?.4:.02);
      const minY=low-pad,maxY=high+pad;
      const xx=i=>12+(samples.length===1?176:i*352/(samples.length-1));
      const yy=v=>18+145-(Number(v)-minY)/(maxY-minY)*145;
      const poly=kind=>samples.map((row,i)=>xx(i)+","+yy(row[kind])).join(" ");
      return '<div class="optical-history-tile"><h4>'+title+'</h4>'+
        '<div class="optical-history-summary"><span>Min <b>'+format(low)+'</b></span>'+
        '<span>Máx <b>'+format(high)+'</b></span>'+
        '<span>Média <b>'+format(record.average)+'</b></span></div>'+
        '<svg viewBox="0 0 380 184" role="img" aria-label="Histórico de '+title+' com média, mínima e máxima">'+
        '<polyline fill="none" stroke="#899caf" stroke-width="1.4" stroke-dasharray="4 4" points="'+poly("min")+'"/>'+
        '<polyline fill="none" stroke="#edac64" stroke-width="1.4" stroke-dasharray="4 4" points="'+poly("max")+'"/>'+
        '<polyline fill="none" stroke="#33b3e2" stroke-width="2.4" points="'+poly("avg")+'"/>'+
        samples.filter((_,i)=>i%Math.max(1,Math.ceil(samples.length/35))===0).map(row=>{
          const i=samples.indexOf(row);
          const stamp=new Date(row.timestamp);
          const when=Number.isFinite(stamp.getTime())?stamp.toLocaleString("pt-BR"):"Leitura";
          return '<circle cx="'+xx(i)+'" cy="'+yy(row.avg)+'" r="3.5" fill="#33b3e2"><title>'+
            this.escape(when+" · Média "+format(row.avg)+" · Mín "+format(row.min)+" · Máx "+format(row.max))+
            '</title></circle>';
        }).join("")+'</svg>'+
        '<small>'+record.count+' leituras · blocos de 5 minutos</small></div>';
    }).join("");
    return '<section class="card"><h3>Histórico de medições ópticas</h3>'+
      '<p class="section-subtitle">Tensão, corrente e potência óptica · retenção de 7 dias. Oscilações não geram eventos de alteração.</p>'+
      '<div class="history-controls">'+select+'</div>'+
      '<div class="optical-history-grid">'+charts+'</div>'+
      '<div class="temp-legend"><span>Média — azul</span><span>Mínima — cinza</span><span>Máxima — laranja</span></div></section>';
  }
  sfpLabel(key) {
    const names={temperature_c:"Temperatura",voltage_v:"Tensão",current_ma:"Corrente do laser",
      rx_dbm:"Potência recebida (RX)",tx_dbm:"Potência transmitida (TX)",
      vendor:"Fabricante",vendorname:"Fabricante",vendor_name:"Fabricante",
      module_present:"Módulo conectado",loss_of_signal:"Perda de sinal",
      media:"Meio de transmissão",compliance:"Padrão Ethernet",bitrate:"Taxa nominal",
      transceiver:"Tipo de módulo",vendor_oui:"OUI do fabricante",
      manufacture_date:"Data de fabricação",port:"Porta",
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
  sfpTemperatureChart(sw) {
    const hours=this.sfpTemperatureHours[sw.id]||24;
    const key=sw.id+"|sfp_temperature|__total__|"+hours+"|sfp";
    const result=this.historyViews[key];
    const options=[[1,"1 hora"],[6,"6 horas"],[12,"12 horas"],[24,"1 dia"],
      [72,"3 dias"],[120,"5 dias"],[168,"7 dias"],[360,"15 dias"],[720,"30 dias"]];
    const select='<label>Período<select class="history-select" data-sfp-temp-hours="'+this.escape(sw.id)+'">'+
      options.map(([value,label])=>'<option value="'+value+'" '+(hours===value?'selected':'')+'>'+label+'</option>').join('')+'</select></label>';
    let content='<p class="muted">Carregando histórico de temperatura…</p>';
    if(result&&!result.loading){
      if(result.error) content='<p class="muted">'+this.escape(result.error)+'</p>';
      else {
        const items=result.items||[];
        const format=n=>Number(n).toLocaleString("pt-BR",{minimumFractionDigits:1,maximumFractionDigits:1})+" °C";
        if(!items.length) content='<p class="muted">Sem medições nesse período. Os registros começam após a atualização.</p>';
        else {
          const lo=Number(result.min),hi=Number(result.max);
          const minY=Math.floor(lo-2),maxY=Math.ceil(hi+2);
          const px=10,py=15,w=880,h=240;
          const x=i=>px+(items.length===1?w/2:i*w/(items.length-1));
          const y=t=>py+h-(Number(t)-minY)/(maxY-minY||1)*h;
          const plotted=items.map((p,i)=>x(i)+","+y(p.avg)).join(" ");
          const lowLine=items.map((p,i)=>x(i)+","+y(p.min)).join(" ");
          const highLine=items.map((p,i)=>x(i)+","+y(p.max)).join(" ");
          const bands=Array.from({length:5},(_,i)=>{const value=minY+(maxY-minY)*i/4;const yy=y(value);
            return '<line x1="10" y1="'+yy+'" x2="890" y2="'+yy+'" stroke="currentColor" opacity=".1"/>'+
              '<text x="16" y="'+(yy-5)+'" fill="currentColor" opacity=".6" font-size="11">'+format(value)+'</text>';}).join("");
          content='<div class="temperature-summary">'+
            '<div><small>Mínima</small><strong>'+format(lo)+'</strong></div>'+
            '<div><small>Máxima</small><strong>'+format(hi)+'</strong></div>'+
            '<div><small>Média</small><strong>'+format(result.average)+'</strong></div></div>'+
            '<div class="temperature-chart"><svg viewBox="0 0 900 280" role="img" aria-label="Histórico da temperatura SFP com valores médios, mínimos e máximos">'+
            bands+'<polyline fill="none" stroke="#42b8ec" stroke-width="2.8" points="'+plotted+'"/>'+
            '<polyline fill="none" stroke="#86a1b7" stroke-width="1.5" stroke-dasharray="5 5" points="'+lowLine+'"/>'+
            '<polyline fill="none" stroke="#eeac65" stroke-width="1.5" stroke-dasharray="5 5" points="'+highLine+'"/>'+
            items.filter((_,i)=>i%Math.max(1,Math.ceil(items.length/70))===0).map(p=>{
              const i=items.indexOf(p),d=new Date(p.timestamp);
              const when=Number.isFinite(d.getTime())?d.toLocaleString("pt-BR"):"Leitura";
              return '<circle cx="'+x(i)+'" cy="'+y(p.avg)+'" r="4" fill="#42b8ec"><title>'+
                this.escape(when+" · Média "+format(p.avg)+" · Mín "+format(p.min)+" · Máx "+format(p.max))+
                '</title></circle>';
            }).join("")+'</svg></div>'+
            '<div class="temp-legend"><span>Média — azul</span><span>Mínima — cinza</span><span>Máxima — laranja</span><span>'+result.count+' leituras</span></div>'+
            '<p class="footnote">Temperatura consolidada em blocos de 5 minutos. Leituras e extremos retidos por até 30 dias.</p>';
        }
      }
    }
    return '<section class="card"><h3>Histórico de temperatura</h3><div class="history-controls">'+select+'</div>'+content+'</section>';
  }
  defaultRange(sw) {
    return this.pref(sw,"options","default_hours",24);
  }
  async setOpticalLimits(sw,metric) {
    const existing=this.pref(sw,"thresholds",metric,null);
    const low=prompt("Primeiro extremo (ex.: -25) de "+this.sfpLabel(metric)+" (aceita números negativos, exemplo: -40). Deixe vazio para remover:",existing?.low??"");
    if(low===null)return;
    if(low.trim()===""){await this.savePreference(sw,"thresholds",metric,null);return;}
    const high=prompt("Segundo extremo (ex.: -15) de "+this.sfpLabel(metric)+" (aceita negativos, exemplo: -10):",existing?.high??"");
    if(high===null)return;
    const parseSigned=value=>Number(String(value).trim().replace("−","-").replace(",","."));
    if(!low.trim()||!high.trim()){this.error="Preencha os dois limites ou remova a configuração.";this.render();return;}
    const a=parseSigned(low),b=parseSigned(high);
    if(!Number.isFinite(a)||!Number.isFinite(b)||a===b||Math.abs(a)>1000||Math.abs(b)>1000){
      this.error="Limites inválidos: informe dois números diferentes entre -1000 e 1000.";this.render();return;
    }
    await this.savePreference(sw,"thresholds",metric,{low:Math.min(a,b),high:Math.max(a,b)});
  }
  renderSfp(sw,compact=false) {
    const raw=sw.sfp?.sfp||{};
    if(!Object.keys(raw).length)return '<p class="empty">Diagnóstico SFP+ indisponível nesta coleta. Consulte Sistema → Saúde das consultas para identificar o erro. Não é possível concluir que o módulo está desconectado.</p>';
    const readings=["rx_dbm","tx_dbm","temperature_c","voltage_v","current_ma"];
    const fields=readings.slice(0,compact?4:5).map(k=>{
      const limits=this.pref(sw,"thresholds",k,null);
      const value=Number(raw[k]);
      const valid=raw[k]!==null&&raw[k]!==undefined&&raw[k]!==""&&Number.isFinite(value);
      const range=limits?(limits.high-limits.low):null;
      const percent=limits&&valid?Math.max(0,Math.min(100,100*(value-limits.low)/range)):0;
      const outside=limits&&valid&&(value<limits.low||value>limits.high);
      const gauge=limits&&valid?'<div class="optical-gauge" title="Posição entre limites personalizados"><span style="width:'+percent+'%;background:'+(outside?'#e0a15b':'#42a7c8')+'"></span></div>':'';
      return '<div class="optical-item"><small>'+this.escape(this.sfpLabel(k))+'</small>'+
        '<strong>'+this.escape(this.sfpValue(k,raw[k]))+'</strong>'+
        (outside?'<small class="threshold-warning">Fora dos limites personalizados</small>':'')+gauge+
        (limits?'<small>'+this.escape(limits.low)+' – '+this.escape(limits.high)+'</small>':'')+
        (!compact?'<button class="threshold-edit" data-sfp-limit-switch="'+this.escape(sw.id)+'" data-sfp-limit-metric="'+k+'">Configurar limites</button>':'')+
        '</div>';
    }).join("");
    const extra=compact?"":Object.entries(raw)
      .filter(([k])=>!readings.includes(k)&&!["temp","voltage","current","rxpower","txpower"].includes(k))
      .map(([k,v])=>'<div class="detail-item"><small>'+this.escape(this.sfpLabel(k))
      +'</small><strong>'+this.escape(v)+'</strong></div>').join("");
    const present=String(raw.module_present||"").trim().toLowerCase();
    const identified=Boolean(raw.vendor||raw.part_number||raw.serial_number||raw.transceiver);
    const presence=present==="yes"||present==="true"||(!present&&identified)?
      '<div class="module-state connected"><span class="module-light"></span>Módulo SFP+ detectado'+(raw.port?' · '+this.escape(raw.port):'')+'</div>':
      (present==="no"||present==="false")&&!identified?
      '<div class="module-state"><span class="module-light"></span>Nenhum módulo óptico informado</div>':"";
    return presence+'<div class="optical-grid">'+fields+'</div>'+(extra?'<h4>Identificação do transceptor</h4><div class="detail-grid">'+extra+'</div>':"");
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
  readableError(error) {
    const describe=(value,depth=0)=>{
      if(value===null||value===undefined)return "";
      if(typeof value==="string")return value==="[object Object]"?"Resposta de erro não estruturada":value;
      if(typeof value!=="object")return String(value);
      if(depth>4)return "Erro com detalhes aninhados";
      const message=value.message??value.detail??value.description??value.error??value.code;
      if(message!==undefined&&message!==value){
        const description=describe(message,depth+1);
        const code=value.code&&value.code!==message?describe(value.code,depth+1):"";
        return [code,description].filter(Boolean).join(" · ");
      }
      try {return JSON.stringify(value);}catch(_){return "Erro não serializável";}
    };
    return describe(error)||"Erro desconhecido";
  }
  async fetchHistory(switchId,mode,port="__total__",hours=24,kind="sfp") {
    const key=switchId+"|"+mode+"|"+port+"|"+hours+"|"+kind;
    // A dashboard refresh and a manual selection can request the same range
    // concurrently. Share the request instead of racing or flooding the HA WS.
    if(this.historyRequests[key])return this.historyRequests[key];
    const previous=this.historyViews[key];
    this.historyViews[key]=previous?.items?.length
      ? {...previous,refreshing:true,loading:false}
      : {loading:true,items:[]};
    this.render();
    const task=(async()=>{
      try {
        const request={type:"ha_oraco/history",entry_id:switchId,mode,port,hours};
        if(mode==="snapshots")request.kind=kind;
        if(mode==="sfp_optical")request.metric=kind;
        const result=await this._hass.connection.sendMessagePromise(request);
        if(result?.error)throw result.error;
        if(!result||typeof result!=="object")throw new Error("Resposta de histórico inválida");
        this.historyViews[key]={...result,items:Array.isArray(result?.items)?result.items:[],loading:false};
      } catch(error) {
        this.historyViews[key]={loading:false,error:this.readableError(error),items:[]};
      } finally {
        delete this.historyRequests[key];
        this.render();
      }
    })();
    this.historyRequests[key]=task;
    return task;
  }
  loadStorageStats(force=false) {
    if(!this._hass||!this.data||this.tab!=="system")return;
    for(const sw of this.data.switches||[]){
      const key=sw.id+"|storage|__total__|24|sfp";
      if(force||!this.historyViews[key])this.fetchHistory(sw.id,"storage");
    }
  }
  storagePanel(sw) {
    const key=sw.id+"|storage|__total__|24|sfp",state=this.historyViews[key];
    if(!state||state.loading)return '<section class="card"><h3>Armazenamento SQLite</h3><p class="muted">Consultando o banco local…</p></section>';
    if(state.error)return '<section class="card"><h3>Armazenamento SQLite</h3><p class="muted">'+this.escape(state.error)+'</p></section>';
    const titles={traffic:"Tráfego detalhado (48 h)",traffic_5m:"Tráfego em blocos (30 dias)",
      traffic_baselines:"Referências de contadores",daily_traffic:"Totais diários (30 dias)",
      sfp_temperature_5m:"Temperatura SFP+ (30 dias)",sfp_optical_5m:"Ópticos RX/TX, corrente e tensão (7 dias)",
      mac_inventory:"Inventário MAC (sem prazo)",snapshots:"Alterações (90 dias)",
      snapshot_daily:"Resumos de auditoria (90 dias)"};
    const size=n=>this.prettyBytes(n||0);
    const rows=Object.entries(state.rows||{}).map(([k,n])=>
      '<tr><td>'+this.escape(titles[k]||k)+'</td><td>'+this.escape(Number(n).toLocaleString("pt-BR"))+'</td><td>'+
      (state.table_bytes?.[k]!==undefined?size(state.table_bytes[k]):"—")+'</td></tr>').join("");
    return '<section class="card"><h3>Armazenamento SQLite</h3>'+
      '<p class="section-subtitle">Medição real do banco compartilhado por todos os switches. O espaço livre interno já foi reservado pelo SQLite e pode ser reutilizado.</p>'+
      '<div class="inventory-stats"><div><small>Arquivo SQLite</small><strong>'+size(state.file_bytes)+'</strong></div>'+
      '<div><small>Dados e índices ocupados</small><strong>'+size(state.used_bytes)+'</strong></div>'+
      '<div><small>Páginas livres internas</small><strong>'+size(state.free_bytes)+'</strong></div></div>'+
      '<div class="scroll"><table><thead><tr><th>Tabela</th><th>Registros</th><th>Espaço estimado*</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+
      '<p class="footnote">*Tamanho de tabela disponível quando o SQLite possui extensão dbstat. Os índices são contabilizados no arquivo, mas podem não estar nesta coluna.</p>'+
      '<button class="history-action" data-refresh-storage="'+this.escape(sw.id)+'">Atualizar medição</button></section>';
  }
  ranges(switchId,port="__total__") {
    const chosen=this.chartHours[switchId+"|"+port]||this.defaultRange((this.data?.switches||[]).find(x=>x.id===switchId)||{preferences:{}});
    const options=[[1,"Última hora"],[6,"6 horas"],[12,"12 horas"],[24,"1 dia"],
      [72,"3 dias"],[120,"5 dias"],[168,"7 dias"],[360,"15 dias"],[720,"30 dias"]];
    return '<select class="history-select" data-chart-hours-select="'+this.escape(switchId)+'" data-port="'+this.escape(port)+'">'+
      options.map(([hours,label])=>'<option value="'+hours+'" '+(hours===chosen?'selected':'')+'>'+label+'</option>').join('')+'</select>';
  }
  prettyBytes(value) {
    const n=Number(value)||0;
    return n>=1e12?(n/1e12).toLocaleString("pt-BR",{maximumFractionDigits:2})+" TB":
      n>=1e9?(n/1e9).toLocaleString("pt-BR",{maximumFractionDigits:2})+" GB":
      n>=1e6?(n/1e6).toLocaleString("pt-BR",{maximumFractionDigits:2})+" MB":
      n>=1e3?(n/1e3).toLocaleString("pt-BR",{maximumFractionDigits:1})+" KB":n+" B";
  }
  dailyTable(switchId,port="__total__") {
    const hours=this.chartHours[switchId+"|"+port]||this.defaultRange((this.data?.switches||[]).find(sw=>sw.id===switchId)||{preferences:{}});
    const current=this.historyViews[switchId+"|traffic|"+port+"|"+hours+"|sfp"];
    const totals=current?.total && typeof current.total==="object" ? current.total : null;
    const status=current?.loading?"Consultando histórico…":current?.error?"Consulta indisponível":current?"Sem totais registrados":"Consultando histórico…";
    const key=switchId+"|daily|"+port+"|24|sfp";
    const result=this.historyViews[key];
    const box='<div class="volume-strip"><div><small>Recebido no período selecionado</small><strong>'+
      (totals?this.prettyBytes(totals.rx_bytes):status)+'</strong></div>'+
      '<div><small>Enviado no período selecionado</small><strong>'+
      (totals?this.prettyBytes(totals.tx_bytes):status)+'</strong></div></div>';
    if(!result)return box+'<p class="muted">Preparando gráfico de volume diário...</p>';
    if(result.loading)return box+'<p class="muted">Consultando totais diários…</p>';
    if(result.error)return box+'<p class="muted">'+this.escape(result.error)+'</p>';
    const chosen=this.chartHours[switchId+"|"+port]||24;
    const limit=Math.min(30,Math.max(1,Math.ceil(chosen/24)));
    const records=result.items.slice(0,limit).reverse(),largest=Math.max(1,...records.flatMap(r=>[r.rx_bytes,r.tx_bytes]));
    const chart='<div class="daily-bars">'+records.map(r=>'<div class="daily-bar-day" title="'+this.escape(r.day)+' · RX '+this.prettyBytes(r.rx_bytes)+' · TX '+this.prettyBytes(r.tx_bytes)+'">'+
      '<div class="bar-pair"><i class="bar-rx" style="height:'+Math.max(1,r.rx_bytes/largest*105)+'px"></i><i class="bar-tx" style="height:'+Math.max(1,r.tx_bytes/largest*105)+'px"></i></div>'+
      '<small>'+this.escape(r.day.slice(5))+'</small></div>').join('')+'</div>';
    return box+'<h4>Volume diário RX/TX · período selecionado</h4>'+chart+
      '<div class="chart-legend"><span>● RX — azul</span><span>● TX — verde</span></div>';
  }
  snapshotDifference(current,previous) {
    if(!previous)return '<p class="muted">Primeiro estado registrado nesta categoria.</p>'+this.snapshotDetails(current);
    const flatten=(obj,prefix="",out={})=>{
      if(obj!==null&&typeof obj==="object"&&!Array.isArray(obj)){
        for(const [key,value] of Object.entries(obj))flatten(value,prefix?prefix+" / "+key:key,out);
      } else out[prefix]=Array.isArray(obj)?JSON.stringify(obj):obj;
      return out;
    };
    const before=flatten(previous),after=flatten(current);
    const keys=[...new Set([...Object.keys(before),...Object.keys(after)])];
    const changes=keys.filter(key=>JSON.stringify(before[key])!==JSON.stringify(after[key]));
    if(!changes.length)return '<p class="muted">Sem diferenças nos campos monitorados.</p>';
    return '<div class="snapshot-diff"><div class="diff-header"><span>Campo</span><span>Antes</span><span>Depois</span></div>'+
      changes.map(key=>'<div class="diff-row"><span>'+this.escape(key)+'</span><del>'+this.snapshotDetails(before[key]??"—")+'</del><ins>'+this.snapshotDetails(after[key]??"—")+'</ins></div>').join("")+
      '</div>';
  }
  snapshotDetails(data,level=0) {
    if(data===null||data===undefined)return "—";
    if(Array.isArray(data))return data.every(v=>v===null||typeof v!=="object")?this.escape(data.join(", ")):'<div class="history-array">'+data.map((value,index)=>'<div class="history-array-item"><small>Item '+(index+1)+'</small>'+this.snapshotDetails(value,level+1)+'</div>').join("")+'</div>';
    if(typeof data!=="object")return this.escape(data);
    if(level>3)return '<span class="muted">Detalhes adicionais</span>';
    return '<div class="history-fields">'+Object.entries(data).map(([key,value])=>
      '<div class="history-field"><span>'+this.escape(this.sfpLabel(key))+'</span><strong>'+
      this.snapshotDetails(value,level+1)+'</strong></div>').join('')+'</div>';
  }
  snapshots(switchId,kind,label) {
    return '<button class="history-action" data-snapshot-switch="'+this.escape(switchId)+'" data-snapshot-kind="'+this.escape(kind)+'" data-snapshot-label="'+this.escape(label)+'">Histórico de '+this.escape(label)+' (90 dias)</button>';
  }
  snapshotDialog() {
    if(!this.snapshotModal)return '';
    const {switchId,kind,label}=this.snapshotModal;
    const key=switchId+"|snapshots|__total__|24|"+kind;
    const result=this.historyViews[key];
    let body='<p class="muted">Carregando verificações…</p>';
    if(result && !result.loading){
      if(result.error)body='<div class="history-error"><strong>Falha ao carregar histórico</strong><p>'+this.escape(this.readableError(result.error))+'</p><button class="history-action" data-retry-snapshot="true">Tentar novamente</button></div>';
      else {
        const days=(result.items||[]).map(item=>item.day?item:{
          day:String(item.timestamp||'').slice(0,10),
          checked_at:item.timestamp,checks:1,changes:1,
          events:[item]
        });
        const unique=[...new Set(days.map(d=>d.day))];
        const current=unique.includes(this.snapshotDay)?this.snapshotDay:unique[0];
        const selected=days.filter(d=>d.day===current);
        const events=selected.flatMap(d=>d.events||[]);
        const checks=selected.reduce((n,d)=>n+Number(d.checks||0),0);
        const changes=selected.reduce((n,d)=>n+Number(d.changes||0),0);
        const list=unique.map(day=>{
          const entries=days.filter(d=>d.day===day);
          const count=entries.reduce((n,d)=>n+Number(d.changes||0),0);
          return '<button class="audit-day '+(day===current?'active':'')+'" data-audit-day="'+this.escape(day)+'"><strong>'+this.escape(day.split('-').reverse().join('/'))+'</strong><span>'+(count?count+' alteração(ões)':'Sem alterações')+'</span></button>';
        }).join('');
        const all=days.flatMap(d=>d.events||[]).sort((a,b)=>new Date(b.timestamp)-new Date(a.timestamp));
        const details=events.map(ev=>{
          const index=all.indexOf(ev);
          const previous=index>=0?all[index+1]?.data:null;
          return '<article class="audit-event"><div class="audit-event-heading">Alteração · '+this.escape(this.formatAuditDate(ev.timestamp,true))+'</div>'+this.snapshotDifference(ev.data,previous)+'</article>';
        }).join('');
        body=unique.length?
          '<div class="audit-layout"><div class="audit-days">'+list+'</div><section class="audit-content"><h3>'+this.escape(current.split('-').reverse().join('/'))+'</h3><p class="section-subtitle">'+checks+' verificações · '+changes+' alterações</p>'+
          (selected[0]?.checked_at?'<p class="muted">Última análise: '+this.escape(this.formatAuditDate(selected[0].checked_at))+'</p>':'')+
          (selected.some(d=>d.events_limited)?'<p class="muted">A visualização carrega somente os 180 eventos mais recentes desta categoria. As contagens diárias abrangem todos os eventos registrados no período de retenção.</p>':'')+
          (details||'<p class="muted">Nenhuma alteração neste dia. O último estado conhecido foi mantido.</p>')+'</section></div>':
          '<p class="muted">Nenhum histórico disponível nos últimos 90 dias.</p>';
      }
    }
    return '<div class="audit-backdrop" data-modal-backdrop="true"><div class="audit-dialog" role="dialog" aria-modal="true" aria-label="Histórico de '+this.escape(label)+'"><div class="audit-header"><div><h2>Histórico de '+this.escape(label)+'</h2><p>Verificações e mudanças detectadas nos últimos 90 dias</p></div><button class="audit-close" data-close-audit="true" aria-label="Fechar histórico" title="Fechar histórico"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button></div><div class="audit-body">'+body+'</div></div></div>';
  }
  trafficChart(id, port=null) {
    const sw=(this.data?.switches||[]).find(x=>x.id===id);
    const hours=this.chartHours[id+"|"+(port||"__total__")]||this.defaultRange(sw||{preferences:{}});
    const key=id+"|traffic|"+(port||"__total__")+"|"+hours+"|sfp";
    const query=this.historyViews[key];
    const persisted=(query?.items||(port ? (sw?.traffic_by_port?.[port]||[]) : (sw?.traffic_history||[]))).map(v=>({rx:Math.max(0,Number(v.rx)||0),tx:Math.max(0,Number(v.tx)||0),timestamp:v.timestamp}));
    const samples=persisted.length?persisted:(port?[]:(this.samples[id]||[]));
    if(query?.error)return '<div class="history-error"><strong>Falha ao consultar histórico</strong><p>'+this.escape(query.error)+'</p><button class="history-action" data-retry-history="'+this.escape(id)+'" data-retry-port="'+this.escape(port||"__total__")+'" data-retry-hours="'+hours+'">Tentar novamente</button></div>';
    if(query?.loading)return '<p class="muted">Buscando amostras no banco SQLite…</p>';
    if(samples.length<2)return '<p class="empty">Nenhum histórico retornado para este intervalo. Verifique a coleta e o armazenamento na aba Sistema.</p>';
    const peak=Math.max(1,...samples.flatMap(v=>[v.rx,v.tx]));
    const rate=n=>n>=1e9?(n/1e9).toFixed(2)+" Gb/s":n>=1e6?(n/1e6).toFixed(1)+" Mb/s":n>=1e3?(n/1e3).toFixed(1)+" kb/s":n.toFixed(0)+" b/s";
    const stamp=entry=>{const date=new Date(entry?.timestamp);return Number.isFinite(date.getTime())?date.toLocaleString("pt-BR"):"—";};
    const dates=samples.map(v=>new Date(v.timestamp).getTime());
    const timeline=dates.every(Number.isFinite)&&dates[dates.length-1]>dates[0];
    const xAt=i=>timeline?30+(dates[i]-dates[0])*740/(dates[dates.length-1]-dates[0]):30+i*740/Math.max(1,samples.length-1);
    const points=key=>samples.map((v,i)=>xAt(i).toFixed(1)
      +','+(159-v[key]/peak*134).toFixed(1)).join(' ');
    const area=key=>"30,159 "+points(key)+" 770,159";
    const labels=[0,.25,.5,.75,1].map(r=>{
      const index=Math.round(r*(samples.length-1));
      return '<text x="'+xAt(index).toFixed(1)+'" y="180" text-anchor="middle" fill="currentColor" opacity=".65" font-size="10">'+
        this.escape(Number.isFinite(dates[index])?new Date(dates[index]).toLocaleString("pt-BR",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}):"")+'</text>';
    }).join("");
    const grid=[26,70,115,159].map(y=>'<line x1="30" x2="770" y1="'+y+'" y2="'+y+'" stroke="currentColor" opacity=".12" stroke-dasharray="4 5"/>').join("");
    return '<svg class="traffic-chart" viewBox="0 0 800 198" role="img" aria-label="Tráfego RX e TX">'
      +grid+labels+'<text x="28" y="17" fill="currentColor" opacity=".7" font-size="12">'+rate(peak)+'</text><polygon points="'+area("rx")+'" fill="#29ade3" opacity=".08"/><polygon points="'+area("tx")+'" fill="#49bf87" opacity=".07"/><polyline points="'+points("rx")+'" fill="none" stroke="#29ade3" stroke-width="2.7" stroke-linejoin="round"/>'
      +'<polyline points="'+points("tx")+'" fill="none" stroke="#49bf87" stroke-width="2.7" stroke-linejoin="round"/>'
      +samples.filter((_,i)=>i%Math.max(1,Math.ceil(samples.length/90))===0).map(v=>{
        const i=samples.indexOf(v),x=xAt(i).toFixed(1);
        return ["rx","tx"].map(key=>'<circle cx="'+x+'" cy="'+(159-v[key]/peak*134).toFixed(1)+
          '" r="3" fill="'+(key==="rx"?"#29ade3":"#49bf87")+'"><title>'+
          this.escape(stamp(v)+" · "+key.toUpperCase()+": "+rate(v[key]))+'</title></circle>').join("");
      }).join("")+'</svg><div class="chart-legend"><span>● RX — azul</span><span>● TX — verde</span><span>'
      +samples.length+' amostras '+(persisted.length?'registradas no banco':'desta sessão')+'</span><span>'+stamp(samples[0])+' — '+stamp(samples[samples.length-1])+'</span></div>';
  }
  pref(sw,category,key,fallback="") {
    return sw.preferences?.[category]?.[key]??fallback;
  }
  async savePreference(sw,category,key,value) {
    try {
      await this._hass.connection.sendMessagePromise({
        type:"ha_oraco/preference",entry_id:sw.id,category,key,value
      });
      sw.preferences ||= {};
      sw.preferences[category] ||= {};
      if(value===null||value==="")delete sw.preferences[category][key];
      else sw.preferences[category][key]=value;
      this.render();
    } catch(error) {
      this.error="Não foi possível salvar preferência: "+this.readableError(error);
      this.render();
    }
  }
  askName(sw,category,key,current) {
    const label=category==="ports"?"Apelido da porta":"Nome do dispositivo";
    const name=prompt(label+" (vazio remove):",current||"");
    if(name!==null)this.savePreference(sw,category,key,name.trim().slice(0,80));
  }
  portDialog() {
    if(!this.portModal)return "";
    const {switchId,number}=this.portModal;
    const sw=(this.data?.switches||[]).find(row=>row.id===switchId);
    const port=sw?.ports?.[number];
    if(!port)return "";
    const fmt=n=>Number(n||0).toLocaleString("pt-BR");
    const name=this.pref(sw,"ports",String(number),"Porta "+number);
    const devices=(sw.mac?.mac_entries||[]).filter(row=>String(row.port).replace(/\D/g,"")===String(number));
    const row=(title,value)=>'<div class="detail-item"><small>'+title+'</small><strong>'+this.escape(value)+'</strong></div>';
    return '<div class="audit-backdrop" data-modal-backdrop="true"><section class="audit-dialog" role="dialog" aria-modal="true" aria-label="Detalhes da porta">'+
      '<div class="audit-header"><div><h2>'+this.escape(name)+'</h2><p>Porta '+this.escape(number)+' · '+(port.up?"Link ativo":"Link inativo")+'</p></div>'+
      '<button class="audit-close" data-close-port="true" aria-label="Fechar">×</button></div>'+
      '<div class="audit-body"><div class="detail-grid">'+row("Velocidade negociada",port.speed||"—")+
      row("Duplex",port.duplex||"—")+row("RX atual",fmt(port.rx_bps)+" bit/s")+
      row("TX atual",fmt(port.tx_bps)+" bit/s")+row("Bytes RX",fmt(port.rx_bytes))+
      row("Bytes TX",fmt(port.tx_bytes))+row("Pacotes RX",fmt(port.rx_packets))+
      row("Pacotes TX",fmt(port.tx_packets))+'</div>'+
      '<h3 class="spaced">Tráfego histórico</h3>'+this.trafficChart(sw.id,String(number))+
      '<div class="history-controls"><label>Intervalo '+this.ranges(sw.id,String(number))+'</label></div>'+
      this.dailyTable(sw.id,String(number))+
      '<h3 class="spaced">MACs aprendidos ('+devices.length+')</h3>'+
      (devices.length?'<div class="detail-grid">'+devices.map(d=>row("VLAN "+(d.vlan||"—"),
        this.pref(sw,"devices",d.mac,d.vendor||d.mac)+" · "+d.mac)).join("")+'</div>':
        '<p class="muted">Nenhum endereço MAC observado nesta porta.</p>')+
      '<div class="history-controls"><button class="history-action" data-port-history="'+this.escape(sw.id)+'" data-port-number="'+this.escape(number)+'">Abrir histórico de tráfego da porta</button>'+
      '<button class="history-action" data-rename-port="'+this.escape(sw.id)+'" data-number="'+this.escape(number)+'">Editar apelido</button></div>'+
      '</div></section></div>';
  }
  topologyBoard(sw) {
    const nodes=(sw.topology?.nodes||[]).filter(n=>n.kind==="port"||n.kind==="learned_mac");
    const documented=Object.entries(sw.preferences?.infrastructure||{}).map(([id,value])=>({
      id:"manual:"+id,kind:"manual",label:value.name,port:String(value.port||"")
    }));
    nodes.push(...documented);
    const ports=nodes.filter(n=>n.kind==="port");
    const macs=nodes.filter(n=>n.kind==="learned_mac");
    const handwritten=nodes.filter(n=>n.kind==="manual");
    const edges=[...(sw.topology?.edges||[])];
    const naturalY=(i,count)=>Math.min(94,Math.max(4,((i+1)/(count+1))*95));
    const byId=new Map();
    const pos=(n,i,count)=>{
      const mac=n.mac||"";
      const key=n.id;
      const recorded=this.pref(sw,"layout",key,null);
      return {x:recorded?.x??(n.kind==="port"?33:72),
              y:recorded?.y??naturalY(i,count),key};
    };
    ports.forEach((n,i)=>byId.set(n.id,pos(n,i,ports.length)));
    macs.forEach((n,i)=>byId.set(n.id,pos(n,i,macs.length)));
    handwritten.forEach((n,i)=>byId.set(n.id,{...pos(n,i,handwritten.length),
      x:this.pref(sw,"layout",n.id,null)?.x??60,
      y:this.pref(sw,"layout",n.id,null)?.y??naturalY(i,handwritten.length)}));
    byId.set("switch",{x:7,y:50});
    const height=Math.max(580,(macs.length+handwritten.length)*64,ports.length*66);
    for(const n of handwritten){
      if(byId.has("port:"+n.port))edges.push({
        from:"port:"+n.port,to:n.id,relation:"manual"
      });
      const info=sw.preferences?.infrastructure?.[n.id.slice(7)]||{};
      for(const mac of info.macs||[]){
        for(const device of macs.filter(row=>row.mac===mac)){
          edges.push({from:n.id,to:device.id,relation:"manual"});
        }
      }
    }
    const lines=edges.filter(e=>byId.has(e.to)&&byId.has(e.from)).map(e=>{
      const a=byId.get(e.from),b=byId.get(e.to);
      return '<line data-wire-from="'+this.escape(e.from)+'" data-wire-to="'+this.escape(e.to)+'" x1="'+((a.x+6)*10)+'" y1="'+(a.y*10)+'" x2="'+((b.x+6)*10)+'" y2="'+(b.y*10)+'" stroke="#4d8d9e" opacity=".65" stroke-width="2" '+(e.relation==="manual"?'stroke-dasharray="6 5"':'')+'/>';
    }).join("");
    const cards=nodes.map(n=>{
      const p=byId.get(n.id);
      const mac=n.mac||"";
      const name=n.kind==="manual"?n.label:n.kind==="port"?this.pref(sw,"ports",n.id.slice(5),n.label):
        (this.pref(sw,"devices",mac,"")||(n.vendor&&n.vendor!=="Desconhecido"?n.vendor:mac));
      return '<div class="board-node '+(n.kind==="port"?"board-port":n.kind==="manual"?"board-manual":"board-mac")+
        '" data-board-node="'+this.escape(n.id)+'" data-board-key="'+this.escape(p.key)+'" data-board-switch="'+this.escape(sw.id)+
        '" style="left:'+p.x+'%;top:'+p.y+'%"><b>'+this.escape(name)+'</b><small>'+
        this.escape(n.kind==="port"?"Porta "+n.id.slice(5):n.kind==="manual"?"Informado manualmente · porta "+n.port:mac)+'</small>'+
        (n.kind==="manual"?'<button class="manual-edit" data-edit-manual="'+this.escape(sw.id)+'" data-manual-id="'+this.escape(n.id.slice(7))+'" title="Associar MACs manualmente" aria-label="Associar MACs manualmente">✎</button><button class="manual-remove" data-remove-manual="'+this.escape(sw.id)+'" data-manual-id="'+this.escape(n.id.slice(7))+'" title="Excluir anotação manual" aria-label="Excluir anotação manual">×</button>':'')+'</div>';
    }).join("");
    return '<div class="board-controls"><span>Arraste os cartões para organizar. As posições ficam salvas no Home Assistant.</span>'+
      '<button class="history-action" data-add-manual="'+this.escape(sw.id)+'">Adicionar equipamento</button>'+
      '<button class="history-action" data-reset-board="'+this.escape(sw.id)+'">Restaurar posições automáticas</button></div>'+
      '<div class="topology-board" data-board="'+this.escape(sw.id)+'" style="height:'+height+'px">'+
      '<div class="board-root">Switch · '+this.escape(sw.host)+'</div>'+
      '<svg viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">'+lines+'</svg>'+cards+'</div>';
  }
  topologyMap(sw) {
    const ports=Object.values(sw.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
    const nodes=sw.topology?.nodes||[],edges=sw.topology?.edges||[];
    if(!ports.length)return '<p class="empty">Sem interfaces identificadas.</p>';
    const rows=ports.map(port=>({
      port, devices:edges.filter(e=>e.from==="port:"+port.port&&e.relation==="mac_learned")
        .map(e=>nodes.find(n=>n.id===e.to)).filter(Boolean)
    }));
    const width=1010, lineHeight=42, gap=22;
    const totalHeight=115+rows.reduce((sum,r)=>sum+Math.max(1,r.devices.length)*lineHeight+gap,0);
    let y=100;
    const parts=['<rect x="18" y="16" width="220" height="55" rx="12" fill="#14324a" stroke="#28b8d3"/>',
      '<text x="37" y="50" fill="#e9f5ff" font-size="17">Switch monitorado</text>'];
    for(const row of rows){
      const length=Math.max(1,row.devices.length),start=y,end=y+length*lineHeight-10,mid=(start+end)/2;
      const status=row.port.up?"#3bbb84":"#6f8494";
      parts.push('<path d="M130 71 V'+mid+' H290" stroke="#376c82" stroke-width="1.5" fill="none"/>',
        '<rect x="290" y="'+(mid-22)+'" width="175" height="44" rx="9" fill="#152c3e" stroke="'+status+'"/>',
        '<circle cx="307" cy="'+mid+'" r="5" fill="'+status+'"/>',
        '<text x="324" y="'+(mid-3)+'" font-size="13" fill="#e8f5ff">Porta '+this.escape(row.port.port)+'</text>',
        '<text x="324" y="'+(mid+13)+'" font-size="10" fill="#a2b5c2">'+this.escape(row.port.speed||"—")+'</text>');
      if(!row.devices.length){
        parts.push('<path d="M465 '+mid+' H525" stroke="#47667a"/>',
          '<text x="545" y="'+(mid+5)+'" font-size="12" fill="#879bad">Nenhum MAC aprendido</text>');
      } else row.devices.forEach((device,index)=>{
        const cy=y+index*lineHeight+14;
        const mac=device.mac||device.id||"Dispositivo";
        const vendor=device.vendor && !["Desconhecido","MAC local/privado","Multicast"].includes(device.vendor)?device.vendor:null;
        const friendly=device.name||((device.label&&device.label!==mac)?device.label:null)||vendor;
        const assigned=this.pref(sw,"devices",mac,"");
        const mainLabel=(assigned||friendly)?(assigned||friendly)+" · "+mac:mac;
        parts.push('<path d="M465 '+mid+' H497 V'+cy+' H535" stroke="'+status+'" stroke-width="1.4" fill="none"/>',
          '<rect x="535" y="'+(cy-16)+'" width="444" height="34" rx="8" fill="#14283b" stroke="#375972"/>',
          '<circle cx="550" cy="'+cy+'" r="4" fill="#45a7d7"/>',
          '<text x="563" y="'+(cy+4)+'" font-size="12" fill="#e5f3ff">'+this.escape(mainLabel)+'</text>');
      });
      y+=length*lineHeight+gap;
    }
    return '<div class="topology-scroll"><svg class="topology-svg" role="img" aria-label="Conexões lógicas individuais dos MACs por porta" viewBox="0 0 '+width+' '+totalHeight+'">'+parts.join('')+'</svg></div><p class="topology-disclaimer">Cada MAC aprendido é representado individualmente. A tabela MAC indica aprendizado lógico, não ligação física direta.</p>';
  }
  escape(v) {
    const display = v === null || v === undefined ? "—" :
      typeof v === "object" ? JSON.stringify(v, null, 2) : String(v);
    return display.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  render() {
    if (!this.shadowRoot) return;
    const switches = this.data?.switches || [];
    const compact=switches[0]?this.pref(switches[0],"options","compact",false):false;
    const fontScale=([0.9,1,1.1,1.2,1.35].includes(switches[0]?.preferences?.options?.font_scale))
      ? switches[0].preferences.options.font_scale : 1;
    const tabs = [["overview","Visão geral"],["ports","Portas"],["history","Histórico"],["sfp","SFP+"],["mac","Dispositivos"],["vlan","VLANs"],["protection","Proteções"],["topology","Mapa de rede"],["system","Sistema"],["services","DHCP / IGMP"],["endpoints","Endpoints"]];
    let body = this.error ? '<section class="card">Não foi possível consultar os dados. '+this.escape(this.error)+'</section>' : "";
    if (!switches.length && !this.error) body = '<section class="card">Nenhum switch configurado ou aguardando dados.</section>';
    for (const sw of switches) {
      const ps = Object.values(sw.ports || {});
      const online = ps.filter(p=>p.up).length;
      const rate = side => ps.reduce((sum,p)=>sum + (Number(p[side+"_bps"]) || 0),0);
      const fmt = n => n >= 1e9 ? (n/1e9).toFixed(2)+" Gb/s" : n>=1e6 ? (n/1e6).toFixed(1)+" Mb/s" : n>=1e3 ? (n/1e3).toFixed(1)+" kb/s" : n.toFixed(0)+" b/s";
      const peak=number=>sw.peaks?.ports?.[number]||{};
      const row = (p) => '<tr class="click-port" data-open-port="'+this.escape(sw.id)+'" data-port-number="'+this.escape(p.port)+'"><td>'+this.escape(this.pref(sw,"ports",String(p.port),"Porta "+p.port))+'</td><td><span class="dot '+(p.up?"ok":"")+'"></span>'+(p.up?"Ativa":"Inativa")+'</td><td>'+this.escape(p.speed)+'</td><td>'+fmt(Number(p.rx_bps)||0)+'</td><td>'+fmt(Number(p.tx_bps)||0)+'</td><td>'+fmt(peak(p.port).rx_bps||0)+'</td><td>'+fmt(peak(p.port).tx_bps||0)+'</td></tr>';

      if (this.tab === "overview") {
        body += '<div class="stats"><section class="card metric"><small>Portas ativas</small><strong>'+online+' / '+ps.length+'</strong></section><section class="card metric"><small>Tráfego RX</small><strong>'+fmt(rate("rx"))+'</strong></section><section class="card metric"><small>Tráfego TX</small><strong>'+fmt(rate("tx"))+'</strong></section><section class="card metric"><small>Firmware</small><strong class="small">'+this.escape(sw.device?.firmware)+'</strong></section></div>';
        body += '<div class="peak-strip"><span>Picos registrados nos últimos 30 dias</span><strong>↓ RX '+fmt(sw.peaks?.total?.rx_bps||0)+'</strong><strong>↑ TX '+fmt(sw.peaks?.total?.tx_bps||0)+'</strong><span class="overview-macs">'+this.escape(sw.mac?.mac_known??0)+' MACs conhecidos</span></div>';

        body += '<section class="card"><h3>Visão das interfaces</h3><p class="section-subtitle">Estado das portas e velocidade negociada</p>'+this.portFace(ps)+'</section>';
        body += '<div class="columns"><section class="card"><h3>Portas e tráfego</h3>'+table(ps.slice(0,12))+'</section><section class="card"><h3>Diagnóstico SFP+</h3>'+this.renderSfp(sw,true)+'<h3 class="spaced">Inventário MAC</h3><p>'+this.escape(sw.mac?.mac_current ?? "—")+' MACs atuais · '+this.escape(sw.mac?.mac_known ?? "—")+' conhecidos</p></section></div>';
      } else if(this.tab === "ports") {
        body += '<section class="card"><h3>Interfaces em tempo real</h3>'+this.portFace(ps)+'</section>'
          +'<section class="card"><h3>Portas e utilização</h3>'+table(ps)+'</section>';
      } else if(this.tab === "history") {
        const selected=this.selectedPort[sw.id]||"__total__";
        const options=['<option value="__total__" '+(selected==="__total__"?'selected':'')+'>Switch inteiro</option>']
          .concat(ps.map(p=>'<option value="'+this.escape(p.port)+'" '+(selected===String(p.port)?'selected':'')+'>Porta '+this.escape(p.port)+'</option>'));
        body += '<section class="card"><h3>Histórico de tráfego</h3><p class="section-subtitle">Médias e picos registrados, com retenção máxima de 30 dias</p>'
          +'<div class="history-controls"><label>Interface<select class="history-select" data-history-port="'+this.escape(sw.id)+'">'+options.join('')+'</select></label>'
          +'<label>Período'+this.ranges(sw.id,selected)+'</label></div>'
          +this.trafficChart(sw.id,selected==="__total__"?null:selected)+this.dailyTable(sw.id,selected)+'</section>';
      }
      else if(this.tab === "sfp") {
        const ddmi=this.ddmiState[sw.id]||{};
        const message=ddmi.loading?"Consultando módulo…":ddmi.status==="ok"?"Atualizado em "+this.formatAuditDate(ddmi.last_success):
          ddmi.status==="rate_limited"||ddmi.status==="busy"?"Aguarde "+ddmi.retry_after+" s antes de consultar novamente.":
          ddmi.status==="error"?"Falha: "+this.escape(ddmi.error):"Coleta automática a cada 60 segundos.";
        body+='<section class="card"><h3>Transceptor óptico · agora</h3>'+
          '<div class="history-controls"><button class="history-action" data-ddmi-refresh="'+this.escape(sw.id)+'" '+(ddmi.loading?'disabled':'')+'>Atualizar DDMI agora</button>'+
          '<span class="muted" role="status">'+message+'</span></div>'+
          '<p class="section-subtitle">Consulta somente leitura, protegida por intervalo mínimo de 30 segundos.</p>'+
          this.renderSfp(sw)+this.snapshots(sw.id,'sfp','SFP+')+'</section>'+
          this.sfpTemperatureChart(sw)+this.sfpOpticalCharts(sw);
      }
      else if(this.tab === "services") body+=this.networkServices(sw);
      else if(this.tab === "endpoints") body+=this.endpointDocs(sw);
      else if(this.tab === "mac") {
        const macData=sw.mac||{};
        const macRows=macData.mac_history_entries||macData.mac_entries||[];
        const filter=this.macSettings(sw);
        const matches=macRows.filter(e=>(filter.port==="all"||String(e.port)===filter.port)&&
          (filter.vlan==="all"||String(e.vlan)===filter.vlan)&&
          (filter.vendor==="all"||(e.vendor||"Desconhecido")===filter.vendor)&&
          (JSON.stringify(e).toLowerCase().includes(filter.query.toLowerCase())||
          this.pref(sw,"devices",e.mac,"").toLowerCase().includes(filter.query.toLowerCase())));
        const maxPage=Math.max(1,Math.ceil(matches.length/filter.page_size));
        const page=Math.min(maxPage,Math.max(1,this.macPages[sw.id]||1));
        const visible=matches.slice((page-1)*filter.page_size,page*filter.page_size);
        const stamp=v=>{if(!v)return '—';const d=new Date(v);return Number.isFinite(d.getTime())?d.toLocaleString('pt-BR'):this.escape(v);};
        const count=sw.oui?.prefix_count||0;
        body+='<section class="card"><h3>Inventário e histórico de dispositivos</h3>'
          +'<div class="inventory-stats"><div><small>MACs presentes</small><strong>'+this.escape(macData.mac_current??0)+'</strong></div>'
          +'<div><small>MACs conhecidos</small><strong>'+this.escape(macData.mac_known??0)+'</strong></div>'
          +'<div><small>Fabricantes identificados</small><strong>'+this.escape(macData.mac_vendor_matched??0)+'</strong></div>'
          +'<div><small>Base IEEE</small><strong>'+this.escape(count?count.toLocaleString('pt-BR')+' prefixos':'Não carregada')+'</strong></div></div>'
          +'<p class="section-subtitle">Histórico persistente: primeira e última observação, porta, VLAN e fabricante. OUI atualizado: '+stamp(sw.oui?.last_updated)+'</p>'
          +'<div class="inventory-filters"><label>Pesquisar<input data-mac-setting="query" data-switch-id="'+this.escape(sw.id)+'" type="search" placeholder="MAC, nome, fabricante" value="'+this.escape(filter.query)+'"></label>'+
          '<label>Porta<select data-mac-setting="port" data-switch-id="'+this.escape(sw.id)+'"><option value="all">Todas as portas</option>'+[...new Set(macRows.map(e=>String(e.port||"")))].sort((a,b)=>Number(a)-Number(b)).map(v=>'<option value="'+this.escape(v)+'" '+(filter.port===v?'selected':'')+'>Porta '+this.escape(v)+'</option>').join("")+'</select></label>'+
          '<label>VLAN<select data-mac-setting="vlan" data-switch-id="'+this.escape(sw.id)+'"><option value="all">Todas as VLANs</option>'+[...new Set(macRows.map(e=>String(e.vlan||"")))].sort().map(v=>'<option value="'+this.escape(v)+'" '+(filter.vlan===v?'selected':'')+'>VLAN '+this.escape(v)+'</option>').join("")+'</select></label>'+
          '<label>Fabricante<select data-mac-setting="vendor" data-switch-id="'+this.escape(sw.id)+'"><option value="all">Todos os fabricantes</option>'+[...new Set(macRows.map(e=>e.vendor||"Desconhecido"))].sort().map(v=>'<option value="'+this.escape(v)+'" '+(filter.vendor===v?'selected':'')+'>'+this.escape(v)+'</option>').join("")+'</select></label>'+
          '<label>Por página<select data-mac-setting="page_size" data-switch-id="'+this.escape(sw.id)+'">'+[25,50,100,200].map(n=>'<option value="'+n+'" '+(filter.page_size===n?'selected':'')+'>'+n+'</option>').join("")+'</select></label>'+
          '<label>Altura<select data-mac-setting="height" data-switch-id="'+this.escape(sw.id)+'">'+[280,440,600,800].map(n=>'<option value="'+n+'" '+(filter.height===n?'selected':'')+'>'+n+' px</option>').join("")+'</select></label>'+
          '<button class="history-action" data-mac-reset="'+this.escape(sw.id)+'">Limpar filtros</button></div>'+
          '<p class="muted" role="status">'+matches.length+' registros encontrados · Página '+page+' de '+maxPage+'</p>'
          +'<div class="scroll mac-table-scroll" style="max-height:'+Number(filter.height)+'px" tabindex="0" aria-label="Tabela de dispositivos, role para navegar"><table><thead><tr><th>Dispositivo / MAC</th><th>Porta</th><th>VLAN</th><th>Fabricante / classificação</th><th>Primeira observação</th><th>Última observação</th></tr></thead><tbody>'
          +visible.map(e=>'<tr><td><button class="mac-name-button" data-name-mac="'+this.escape(sw.id)+'" data-mac="'+this.escape(e.mac)+'" title="Editar nome do dispositivo">'+this.escape(this.pref(sw,"devices",e.mac,"Nomear"))+'</button><small>'+this.escape(e.mac)+'</small></td><td>'+this.escape(this.pref(sw,"ports",String(e.port),"Porta "+e.port))+'</td><td>'+this.escape(e.vlan)+'</td><td>'+this.escape(e.vendor||e.classification)+'</td><td>'+stamp(e.first_seen)+'</td><td>'+stamp(e.last_seen)+'</td></tr>').join('')
          +'</tbody></table></div><div class="mac-pager"><button class="history-action" data-mac-page="'+this.escape(sw.id)+'" data-page="'+(page-1)+'" '+(page<=1?'disabled':'')+'>Anterior</button><span>Página '+page+' / '+maxPage+'</span><button class="history-action" data-mac-page="'+this.escape(sw.id)+'" data-page="'+(page+1)+'" '+(page>=maxPage?'disabled':'')+'>Próxima</button></div><p class="footnote">Exibindo até 200 registros recentes do histórico do switch. MACs administrados localmente não permitem atribuição confiável por OUI.</p></section>';
      }
      else if(this.tab === "topology") body += '<section class="card"><h3>Mapa lógico · edição de posições</h3><p class="section-subtitle">Organização visual personalizável; conexões representam MACs aprendidos, não enlaces físicos confirmados.</p>'+this.topologyBoard(sw)+'<details><summary>Visualização automática por porta</summary>'+this.topologyMap(sw)+'</details></section>';
      else if(this.tab === "protection") {
        const net=sw.network||{};
        const iso=Object.values(net.isolation?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const stp=Object.values(net.stp_ports?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const storm=Object.values(net.storm_control?.ports||{}).sort((a,b)=>Number(a.port)-Number(b.port));
        const status=rows=>rows.length?'':'<p class="empty">Sem dados disponíveis para este recurso.</p>';
        const tbl=(cols,rows)=>'<div class="scroll"><table><thead><tr>'+cols.map(c=>'<th>'+c+'</th>').join('')+'</tr></thead><tbody>'+rows.join('')+'</tbody></table></div>';
        const global=net.stp_global||{};
        if(Object.keys(global).length) {
          const labels={status:"Estado",version:"Protocolo selecionado",priority:"Prioridade da bridge",
            max_age:"Tempo máximo",hello_time:"Intervalo Hello",forward_delay:"Atraso de encaminhamento",
            root_priority:"Prioridade da raiz",root_mac:"MAC da raiz",root_path_cost:"Custo até a raiz",
            root_port:"Porta raiz",root_max_age:"Max Age da raiz",root_hello_time:"Hello da raiz",
            root_forward_delay:"Forward Delay da raiz"};
          body+='<section class="card"><h3>STP / RSTP global <span class="help-tip" role="img" tabindex="0" aria-label="Protocolo de proteção contra loops. Quando desativado, os parâmetros configurados não significam proteção ativa." title="Protocolo de proteção contra loops. Quando desativado, os parâmetros configurados não significam proteção ativa.">?</span></h3><p class="section-subtitle">Estado atual: '+(global.enabled?'Ativado':'Desativado')+'</p><div class="detail-grid">'
            +Object.entries(global).filter(([k])=>k!=="enabled").map(([k,v])=>'<div class="detail-item"><small>'+this.escape(labels[k]||k)+'</small><strong>'+this.escape(v)+'</strong></div>').join('')
            +'</div>'+this.snapshots(sw.id,'stp_global','STP global')+'</section>';
        }
        const aggregate=net.aggregation;
        if(aggregate) {
          body+='<section class="card"><h3>Agregação de portas <span class="help-tip" role="img" tabindex="0" aria-label="Grupos de interfaces operando como um enlace lógico, por agregação estática ou LACP." title="Grupos de interfaces operando como um enlace lógico, por agregação estática ou LACP.">?</span></h3><p class="section-subtitle">'+this.escape(aggregate.count)+' grupo(s) identificado(s)</p>'
            +(aggregate.groups?.length?tbl(['Grupo','Tipo','Membros','Porta agregada'],aggregate.groups.map(g=>'<tr><td>'+this.escape(g.group)+'</td><td>'+this.escape(g.type)+'</td><td>'+this.escape(g.members)+'</td><td>'+this.escape(g.aggregated_port)+'</td></tr>')):'<p class="empty">Nenhum grupo de agregação configurado.</p>')+this.snapshots(sw.id,'aggregation','Agregação')+'</section>';
        }
        body+='<section class="card"><h3>Isolamento de portas <span class="help-tip" role="img" tabindex="0" aria-label="Listas de portas que o firmware associa ao isolamento. A direção do bloqueio depende do modelo; não significa automaticamente que todas estejam isoladas." title="Listas de portas que o firmware associa ao isolamento. A direção do bloqueio depende do modelo; não significa automaticamente que todas estejam isoladas.">?</span></h3><p class="section-subtitle">Listas apresentadas pelo firmware; o sentido das restrições ainda requer validação.</p>'+status(iso)
          +(iso.length?tbl(['Porta','Lista informada','Portas listadas'],iso.map(p=>'<tr><td>Porta '+this.escape(p.port)+'</td><td>'+this.escape(p.raw_list)+'</td><td>'+this.escape(p.listed_ports?.join(', '))+'</td></tr>')):'') +this.snapshots(sw.id,'isolation','Isolamento')+'</section>';
        body+='<section class="card"><h3>Spanning Tree — portas <span class="help-tip" role="img" tabindex="0" aria-label="Estado e função STP de cada porta. Forwarding indica encaminhamento; STP global desativado não protege contra loops." title="Estado e função STP de cada porta. Forwarding indica encaminhamento; STP global desativado não protege contra loops.">?</span></h3><p class="section-subtitle">Estado, função, custo e parâmetros efetivos de STP.</p>'+status(stp)
          +(stp.length?tbl(['Porta','Estado','Função','Custo configurado','Custo efetivo','Prioridade','P2P efetivo','Edge efetivo'],stp.map(p=>
            '<tr><td>Porta '+this.escape(p.port)+'</td><td>'+this.escape(p.state)+'</td><td>'+this.escape(p.role)+'</td><td>'+this.escape(p.path_cost_config)+'</td><td>'+this.escape(p.path_cost_actual)+'</td><td>'+this.escape(p.priority)+'</td><td>'+this.escape(p.p2p_actual)+'</td><td>'+this.escape(p.edge_actual)+'</td></tr>')):'') +this.snapshots(sw.id,'stp_ports','STP por porta')+'</section>';
        const stormValue=v=>v===null||v===undefined?'Desativado':this.escape(v)+' kbit/s';
        body+='<section class="card"><h3>Controle de tempestades <span class="help-tip" role="img" tabindex="0" aria-label="Limites que restringem tráfego broadcast, multicast e unicast desconhecido para reduzir tempestades de rede." title="Limites que restringem tráfego broadcast, multicast e unicast desconhecido para reduzir tempestades de rede.">?</span></h3><p class="section-subtitle">Limites configurados por interface. Desativado não significa tráfego zero.</p>'+status(storm)
          +(storm.length?tbl(['Porta','Broadcast','Multicast conhecido','Multicast desconhecido','Unicast desconhecido'],storm.map(p=>
            '<tr><td>Porta '+this.escape(p.port)+'</td><td>'+stormValue(p.broadcast_kbps)+'</td><td>'+stormValue(p.known_multicast_kbps)+'</td><td>'+stormValue(p.unknown_multicast_kbps)+'</td><td>'+stormValue(p.unknown_unicast_kbps)+'</td></tr>')):'') +this.snapshots(sw.id,'storm_control','Storm Control')+'</section>';
      }
      else if(this.tab === "system") {
        body+=this.storagePanel(sw);
        const oui=sw.oui||{};
        const sources=Object.entries(oui.sources||{});
        const time=value=>{if(!value)return '—';const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString('pt-BR'):this.escape(value);};
        body+='<section class="card"><h3>Informações do equipamento</h3>'+Object.entries(sw.device||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v)+'</b></div>').join("")+'</section>';
        body+='<section class="card"><h3>Base IEEE de fabricantes</h3><div class="inventory-stats">'
          +'<div><small>Prefixos carregados</small><strong>'+this.escape(Number(oui.prefix_count||0).toLocaleString("pt-BR"))+'</strong></div>'
          +'<div><small>Última atualização</small><strong class="system-date">'+time(oui.last_updated)+'</strong></div>'
          +'<div><small>Última tentativa</small><strong class="system-date">'+time(oui.last_attempt)+'</strong></div></div>'
          +(sources.length?sources.map(([name,detail])=>'<div class="kv"><span>'+this.escape(name)+'</span><b>'+this.escape(detail.status)+(detail.count!==undefined?' · '+this.escape(detail.count)+' registros':'')+(detail.error?' · '+this.escape(detail.error):'')+'</b></div>').join(""):'<p class="section-subtitle">Ainda não há detalhes da tentativa nesta sessão. A base carregada anteriormente continua disponível.</p>')
          +'</section>';
        const changes=sw.recent_changes||[];
        const labels={sfp:"SFP+",vlan_ports:"VLANs",isolation:"Isolamento",stp_ports:"STP por porta",storm_control:"Storm Control",stp_global:"STP global",aggregation:"Agregação"};
        body+='<section class="card"><h3>Histórico de mudanças detectadas</h3><p class="section-subtitle">Snapshots reais no banco, com retenção de 90 dias. Valores repetidos não criam novos eventos.</p>'
          +(changes.length?'<div class="event-list">'+changes.slice(0,20).map(ev=>'<div class="event-item"><span class="event-dot"></span><span>'+this.escape(labels[ev.kind]||ev.kind)+'</span><time>'+time(ev.timestamp)+'</time></div>').join("")+'</div>':'<p class="empty">Ainda não há snapshots registrados.</p>')+'</section>';
        body+='<section class="card"><h3>Saúde das consultas</h3>'+Object.entries(sw.diagnostics?.endpoints||{}).map(([k,v])=>'<div class="kv"><span>'+this.escape(k)+'</span><b>'+this.escape(v.status)+(v.error?' · '+this.escape(v.error):'')+(v.detail?'<small class="endpoint-detail">'+this.escape(v.detail)+'</small>':'')+(v.history_error?'<small class="endpoint-detail">Histórico: '+this.escape(v.history_error)+'</small>':'')+'</b></div>').join("")+'</section>';
      }
      else if(this.tab === "vlan") {
        const vlans=sw.network?.vlan_ports?.ports||{};
        const vlanRows=Object.values(vlans).sort((a,b)=>Number(a.port)-Number(b.port));
        const fmt=items=>Array.isArray(items)&&items.length?items.map(v=>'<span class="vlan-pill">'+this.escape(v)+'</span>').join(" "):'<span class="muted">—</span>';
        body += '<section class="card"><h3>Configuração de VLANs por porta</h3><p class="section-subtitle">Leitura da tabela de estado do switch; nenhuma configuração é alterada.</p>'
          +(vlanRows.length?'<div class="scroll"><table class="vlan-table"><thead><tr><th>Porta</th><th>Modo</th><th>Access</th><th>Nativa / PVID*</th><th>Tagged</th><th>Untagged</th><th>VLANs permitidas</th></tr></thead><tbody>'
            +vlanRows.map(p=>'<tr><td><strong>Porta '+this.escape(p.port)+'</strong></td><td><span class="mode-pill">'+this.escape((p.mode||"—").toUpperCase())+'</span>'
              +(p.accepted_frames?'<small class="mode-detail">'+this.escape(p.accepted_frames)+'</small>':"")+'</td><td>'+this.escape(p.access_vlan??"—")+'</td><td>'+this.escape(p.native_vlan??"—")+'</td><td>'+fmt(p.tagged_vlans)+'</td><td>'+fmt(p.untagged_vlans)+'</td><td>'+fmt(p.allowed_vlans)+'</td></tr>').join("")+'</tbody></table></div>'
            :'<p class="empty">Nenhuma tabela de VLANs disponível ainda.</p>')
          +'<p class="footnote">* A interface do firmware identifica a coluna como Native VLAN. Não assumimos que represente todas as configurações de PVID ou isolamento.</p>'+this.snapshots(sw.id,'vlan_ports','VLANs')+'</section>';
      }
      else body += '<section class="card"><h3>'+this.escape(tabs.find(t=>t[0]===this.tab)?.[1])+'</h3><p>Esta área será preenchida automaticamente quando os dados forem disponibilizados pela integração e validados no firmware. Nenhum dado fictício é exibido.</p></section>';
      function table(items) { return '<div class="scroll"><table><thead><tr><th>Interface</th><th>Link</th><th>Velocidade</th><th>RX</th><th>TX</th><th>Pico RX</th><th>Pico TX</th></tr></thead><tbody>'+items.map(row).join("")+'</tbody></table></div>'; }
    }
    this.shadowRoot.innerHTML = `<style>
      :host{--hora-scale:${fontScale}}
      :host { display:block; min-height:100%; color:var(--primary-text-color); background:var(--primary-background-color); font-family:Roboto,"Arial",sans-serif; }
      *{box-sizing:border-box} main{max-width:1480px;margin:auto;padding:24px;} header{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:22px}
      .brand-wrap{display:flex;flex-direction:column;gap:4px}.brand-subtitle{font-size:12px;color:var(--secondary-text-color);padding-left:50px}.brand{display:flex;align-items:center;gap:12px}.brand img{width:38px;height:38px;object-fit:contain} h1{font-size:24px;font-weight:500;margin:0}h2{font-size:19px;font-weight:500;margin:0}h3{font-size:15px;font-weight:500;margin:0 0 18px}
      nav{display:flex;gap:6px;overflow-x:auto;border-bottom:1px solid var(--divider-color);margin-bottom:24px}
      button{font:inherit;cursor:pointer;background:transparent;color:var(--secondary-text-color);border:0;border-bottom:2px solid transparent;padding:13px 15px;white-space:nowrap}
      button.selected{color:var(--primary-color);border-color:var(--primary-color)}button:hover{color:var(--primary-text-color)}
      button.refresh{border:1px solid var(--divider-color);border-radius:8px;padding:9px 16px}
      .heading{display:flex;gap:12px;align-items:center;justify-content:space-between;margin:24px 0 14px}.heading span,small,p{color:var(--secondary-text-color)}
      .stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.card{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:20px;margin-bottom:16px}
      .metric{position:relative;overflow:hidden;isolation:isolate;box-shadow:0 8px 26px rgba(0,0,0,.07)}
      .metric:before{content:"";position:absolute;inset:0 0 auto;height:3px;background:linear-gradient(90deg,#178dff,#2dd4bb)}
      .metric:nth-child(2):before{background:linear-gradient(90deg,#247dff,#29c7eb)}
      .metric:nth-child(3):before{background:linear-gradient(90deg,#21bd83,#7bdfb2)}
      .metric:nth-child(4):before{background:linear-gradient(90deg,#7d84fa,#aa93f4)}
      .metric small{display:block;font-size:12px;margin-bottom:11px;color:var(--secondary-text-color)}
      .metric strong{font-size:clamp(21px,2vw,28px);font-weight:650;letter-spacing:-.5px}
      .metric strong.small{font-size:16px;line-height:1.5}
      .optical-gauge{height:5px;background:var(--divider-color);border-radius:4px;overflow:hidden;margin-top:8px}
      .optical-gauge span{display:block;height:100%;border-radius:4px}
      .threshold-warning{color:#df965a!important}.threshold-edit{font-size:11px;padding:6px 0;border:0;color:var(--primary-color)}
      .snapshot-diff{display:grid;gap:3px;min-width:0}
      .diff-header,.diff-row{display:grid;grid-template-columns:minmax(130px,1.3fr) repeat(2,minmax(100px,1fr));align-items:start;gap:8px;padding:8px;border-bottom:1px solid var(--divider-color);font-size:12px}
      .diff-header{font-weight:600;color:var(--secondary-text-color)}.diff-row>*{overflow-wrap:anywhere}
      .diff-row del{color:#c47f7f;text-decoration:none}.diff-row ins{color:#58b993;text-decoration:none}
      @media(max-width:600px){.diff-header,.diff-row{grid-template-columns:minmax(80px,1fr) repeat(2,minmax(65px,1fr));font-size:11px}}
      .board-controls{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:9px;margin:12px 0;font-size:12px;color:var(--secondary-text-color)}
      .topology-board{position:relative;min-width:650px;overflow:hidden;border-radius:12px;border:1px solid var(--divider-color);background:var(--secondary-background-color)}
      .topology-board svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
      .board-root{position:absolute;left:2%;top:50%;transform:translateY(-50%);font-weight:600;font-size:13px;color:var(--primary-text-color)}
      .board-node{position:absolute;z-index:2;width:125px;min-height:43px;transform:translateY(-50%);padding:8px 10px;border:1px solid var(--primary-color);border-radius:9px;background:var(--card-background-color);color:var(--primary-text-color);cursor:grab;touch-action:none;user-select:none;box-shadow:0 3px 12px rgba(0,0,0,.15)}
      .board-node:active{cursor:grabbing}.board-node b{display:block;font-size:11px;overflow-wrap:anywhere}.board-node small{font-size:10px}
      .manual-edit{position:absolute;right:18px;top:0;padding:0 4px;font-size:13px;border:0}
      .manual-remove{position:absolute;right:1px;top:0;padding:0 4px;font-size:14px;border:0}
      .board-port{border-color:#3bbb84}.board-mac{border-color:#45a7d7}.board-manual{border-style:dashed;border-color:#daa057}
      .header-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
      .compact-view .card{padding:13px;margin-bottom:10px}
      .compact-view .stats{gap:9px}.compact-view .metric strong{font-size:20px}
      .compact-view .optical-item{padding:10px}
      .inventory-filters{display:flex;flex-wrap:wrap;gap:9px;margin:14px 0;align-items:flex-end}
      .inventory-filters label,.endpoint-picker,.scale-picker{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--secondary-text-color)}
      .mac-table-scroll{overflow:auto;min-height:120px;overscroll-behavior:contain;border:1px solid var(--divider-color);border-radius:9px}
      .mac-table-scroll th{top:0}
      .mac-pager{display:flex;gap:12px;align-items:center;justify-content:flex-end;padding:12px 0;flex-wrap:wrap}
      .mac-pager button:disabled,.history-action:disabled{opacity:.45;cursor:not-allowed}
      .endpoint-picker select,.scale-picker select{border:1px solid var(--divider-color);border-radius:9px;padding:9px;background:var(--card-background-color);color:var(--primary-text-color);max-width:100%}
      .endpoint-json{max-height:360px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;background:var(--secondary-background-color);border-radius:8px;font-size:12px}
      .endpoint-picker{margin-bottom:16px}
      @media(max-width:720px){.inventory-filters label{width:100%;min-width:0}.inventory-filters input,.inventory-filters select{width:100%;min-width:0}.header-actions{flex-wrap:wrap}.mac-pager{justify-content:center}}
      @media(max-width:390px){.card{padding:12px}.endpoint-json{font-size:11px}}
      .inventory-filters input,.inventory-filters select{border:1px solid var(--divider-color);border-radius:9px;padding:9px;background:var(--card-background-color);color:var(--primary-text-color);min-width:170px}
      .mac-name-button{padding:3px 0;border:0;color:var(--primary-color);font-weight:600;text-align:left}
      td .mac-name-button+small{display:block;font-size:11px}
      .click-port{cursor:pointer}.click-port:hover{background:var(--secondary-background-color)}
      .card{box-shadow:0 7px 24px rgba(0,0,0,.055)}
      .heading{border-bottom:1px solid var(--divider-color);padding-bottom:13px;margin-bottom:20px}
      .traffic-chart{background:linear-gradient(180deg,transparent,color-mix(in srgb,var(--primary-color) 3%,transparent));border-radius:11px}
      table tbody tr:hover{background:var(--secondary-background-color)}
      button:focus-visible,input:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}


      /* Font-scale respects document width; never zoom the host's layout box. */
      :host main,:host .audit-dialog{font-size:calc(14px * var(--hora-scale))}
      :host :is(nav button,button,input,select,label,td,th,summary,.muted,.section-subtitle,.footnote,.detail-item,.detail-grid, .kv){font-size:calc(12px * var(--hora-scale))}
      :host h1{font-size:calc(24px * var(--hora-scale))}
      :host h2{font-size:calc(19px * var(--hora-scale))}
      :host h3{font-size:calc(15px * var(--hora-scale))}
      :host .metric strong{font-size:clamp(20px,calc(24px * var(--hora-scale)),36px)}
      :host .card{overflow-wrap:break-word}
      /* 0.4.28: consistent, accessible data-heavy dashboard surfaces */
      :host{--hora-rx:#29ade3;--hora-tx:#49bf87;--hora-warn:#d99b55}
      main{width:100%;max-width:1560px;padding:clamp(12px,2.2vw,30px)}
      header{padding:6px 0 12px;border-bottom:1px solid var(--divider-color)}
      .brand{font-weight:680;letter-spacing:-.6px}
      .brand-subtitle{font-size:13px;line-height:1.5}
      nav{gap:3px;scrollbar-width:thin;position:relative}
      nav button{border-radius:9px 9px 0 0;transition:color .16s,background .16s}
      nav button.selected{background:var(--secondary-background-color);font-weight:650}
      .card{border-radius:15px;box-shadow:0 3px 15px rgba(0,0,0,.045);min-width:0}
      .card h3{letter-spacing:-.2px}
      .metric{min-height:108px;display:flex;flex-direction:column;justify-content:space-between}
      .metric strong{font-variant-numeric:tabular-nums}
      .stats,.columns,.detail-grid,.volume-strip{min-width:0}
      .scroll{max-width:100%;border-radius:10px;scrollbar-width:thin}
      table{font-variant-numeric:tabular-nums}
      th{position:sticky;top:0;background:var(--card-background-color);z-index:1;font-size:11px;letter-spacing:.025em;text-transform:uppercase}
      tbody tr:nth-child(even){background:color-mix(in srgb,var(--secondary-background-color) 42%,transparent)}
      td{vertical-align:middle}
      .history-array{display:grid;gap:8px;min-width:0}.history-array-item{padding:9px;border:1px solid var(--divider-color);border-radius:8px;min-width:0}.history-array-item>small{display:block;margin-bottom:6px}
      .optical-item .threshold-edit{display:block;margin-top:10px;padding:7px 9px;border:1px solid var(--divider-color);border-radius:7px;white-space:normal;text-align:left}
      .optical-item strong{display:block;line-height:1.45}
      .history-error{padding:13px 16px;border:1px solid var(--error-color,#c75e5e);border-radius:10px;margin:12px 0}.history-error p{overflow-wrap:anywhere}
      .history-controls{border-radius:12px;padding:12px;background:var(--secondary-background-color)}
      .history-select,.inventory-filters select{outline-offset:2px}
      .history-select:focus-visible,.inventory-filters select:focus-visible{outline:2px solid var(--primary-color)}
      .traffic-chart,.temperature-chart,.optical-history-tile svg{overflow:visible}
      .traffic-chart{max-height:240px;border:1px solid var(--divider-color);padding:8px}
      .temperature-chart{background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:12px;padding:10px}
      .temperature-summary strong,.volume-strip strong{font-variant-numeric:tabular-nums;letter-spacing:-.35px}
      .optical-history-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
      .optical-history-tile{transition:border-color .15s,box-shadow .15s}
      .optical-history-tile:hover{border-color:var(--primary-color);box-shadow:0 3px 18px rgba(0,0,0,.08)}
      .optical-history-tile h4{font-size:14px;letter-spacing:-.1px}
      .optical-history-tile svg{max-height:210px;margin:12px 0}
      .optical-history-summary{border-bottom:1px solid var(--divider-color);padding-bottom:12px}
      .chart-legend,.temp-legend{display:flex;align-items:center;gap:15px;flex-wrap:wrap;line-height:1.6}
      .port{transition:transform .14s,border-color .14s,background .14s}
      .port:hover{transform:translateY(-2px);border-color:var(--primary-color)}
      .audit-dialog{width:min(1100px,100%);max-height:92dvh}
      .audit-body{overscroll-behavior:contain}
      .diff-row{border-radius:5px}
      .diff-row:nth-child(even){background:var(--secondary-background-color)}
      .board-node:focus-visible{outline:3px solid var(--primary-color);outline-offset:3px}
      button{transition:background-color .14s,color .14s,border-color .14s}
      button:disabled{opacity:.45;cursor:not-allowed}
      @media(max-width:1050px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.columns{grid-template-columns:1fr}}
      @media(max-width:720px){main{padding:12px}.card{padding:14px}.optical-history-grid{grid-template-columns:1fr}.temperature-summary{gap:6px}.temperature-summary>div{padding:10px}.temperature-summary strong{font-size:17px}.history-controls{padding:10px}.stats{gap:9px}.brand-subtitle{padding-left:0}.audit-header{padding:14px}.audit-body{padding:12px}}
      @media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important;animation:none!important}}
      .columns{display:grid;grid-template-columns:2fr 1fr;gap:16px}.port-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(82px,1fr));gap:10px}.port{background:var(--secondary-background-color);border:1px solid var(--divider-color);padding:12px;border-radius:8px;text-align:center}
      .port.active{border-color:var(--success-color,#4caf50)}.port b{display:block;font-size:16px}.port span{font-size:11px;color:var(--secondary-text-color)}.scroll{overflow:auto}
      .traffic-chart{display:block;width:100%;height:auto;max-height:200px} table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:12px 10px;border-bottom:1px solid var(--divider-color);white-space:nowrap}th{font-weight:500;color:var(--secondary-text-color)}
      .dot{display:inline-block;width:8px;height:8px;background:var(--disabled-text-color);border-radius:50%;margin-right:8px}.dot.ok{background:var(--success-color,#4caf50)}
      input[type=search]{width:100%;padding:12px 14px;border:1px solid var(--divider-color);border-radius:8px;background:var(--secondary-background-color);color:var(--primary-text-color);margin-bottom:12px} .kv{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--divider-color);gap:15px}.kv span{color:var(--secondary-text-color)}

      .vlan-table td{vertical-align:middle}.vlan-pill{display:inline-block;padding:3px 7px;margin:2px;border-radius:6px;background:var(--secondary-background-color);border:1px solid var(--divider-color);font-size:11px}.mode-pill{display:inline-block;border-radius:7px;padding:5px 8px;background:var(--secondary-background-color);border:1px solid var(--divider-color);font-size:10px;font-weight:650}.mode-detail{display:block;margin-top:5px;color:var(--secondary-text-color)}.muted{color:var(--secondary-text-color)}
      .range-list{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 18px}
      .range{border:1px solid var(--divider-color);border-radius:8px;padding:8px 11px;font-size:12px;color:var(--primary-text-color)}
      .range.chosen{border-color:var(--primary-color);color:var(--primary-color);background:var(--secondary-background-color)}
      .history-action{border:1px solid var(--divider-color);border-radius:9px;padding:11px 13px;margin:16px 0;color:var(--primary-text-color)}
      .snapshot-list{margin:18px 0}.snapshot-list details{border:1px solid var(--divider-color);border-radius:8px;padding:12px;margin:7px 0}.snapshot-list summary{cursor:pointer}.snapshot-list pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}
      .endpoint-detail{display:block;font-weight:400;color:var(--secondary-text-color);max-width:650px;white-space:normal;overflow-wrap:anywhere;margin-top:4px}
      .audit-backdrop{position:fixed;z-index:1000;inset:0;background:rgba(0,0,0,.72);display:flex;align-items:center;justify-content:center;padding:20px}
      .audit-dialog{display:flex;flex-direction:column;width:min(100%,1020px);max-height:min(88vh,940px);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:16px;box-shadow:0 26px 90px rgba(0,0,0,.48);overflow:hidden}
      .audit-header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:20px 24px;border-bottom:1px solid var(--divider-color)}
      .audit-header h2{font-weight:650;margin:0;font-size:19px}.audit-header p{margin:6px 0 0;color:var(--secondary-text-color);font-size:12px}
      .audit-close{appearance:none;display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;flex:0 0 40px;width:40px;height:40px;min-width:40px;min-height:40px;padding:0;line-height:1;border:1px solid var(--divider-color);border-radius:10px;color:var(--primary-text-color);background:var(--secondary-background-color);cursor:pointer}
      .audit-close svg{display:block;pointer-events:none}
      .audit-close:hover{background:var(--primary-color);color:var(--text-primary-color,#fff)}
      .audit-close:focus-visible,.audit-day:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
      .audit-header>div{flex:1;min-width:0}
      .audit-header h2,.audit-header p{line-height:1.4;overflow-wrap:anywhere}
      .audit-body{min-height:130px;overflow:auto;padding:18px 22px}
      .audit-layout{display:grid;grid-template-columns:minmax(190px,235px) minmax(0,1fr);gap:20px;align-items:start}
      .audit-days{display:flex;flex-direction:column;gap:8px;max-height:65vh;overflow-y:auto;overscroll-behavior:contain}
      .audit-day{display:flex;flex-direction:column;gap:5px;text-align:left;padding:12px;min-width:0;border:1px solid var(--divider-color);border-radius:9px;color:var(--primary-text-color);font-size:12px}
      .audit-day span{font-size:11px;color:var(--secondary-text-color)}
      .audit-day.active{background:var(--secondary-background-color);border-color:var(--primary-color)}
      .audit-content{min-width:0;max-height:65vh;overflow:auto;padding:4px 2px 16px;overscroll-behavior:contain}
      .audit-content h3{margin:0 0 8px;line-height:1.35}.audit-content .section-subtitle{margin:0 0 12px;line-height:1.45}.audit-content .muted{line-height:1.5}
      .audit-event{margin-top:18px;border:1px solid var(--divider-color);border-radius:10px;padding:12px;max-width:100%;overflow:hidden}
      .audit-event-heading{font-weight:600;margin-bottom:12px}
      .audit-content .history-fields{display:grid;gap:7px;min-width:0;width:100%}
      .audit-content .history-field{display:grid;grid-template-columns:minmax(110px,1fr) minmax(0,2fr);align-items:start;gap:12px}
      .audit-content .history-field>span{text-align:left;overflow-wrap:anywhere}
      .audit-content .history-field>strong{text-align:left;min-width:0;overflow-wrap:anywhere}
      @media(max-width:650px){.audit-backdrop{padding:8px}.audit-layout{grid-template-columns:1fr}.audit-days{flex-direction:row;max-height:none;overflow-x:auto}.audit-day{min-width:145px}.audit-content{max-height:54vh}.audit-body{padding:12px}}
      .module-state{display:flex;align-items:center;gap:10px;padding:12px;margin:12px 0;border-radius:10px;background:var(--secondary-background-color);font-size:12px}
      .module-light{width:8px;height:8px;border-radius:50%;background:var(--disabled-text-color)}
      .module-state.connected .module-light{background:#3bbb84}
      .help-tip{display:inline-grid;place-items:center;width:18px;height:18px;font-size:11px;font-weight:700;border:1px solid var(--secondary-text-color);border-radius:50%;color:var(--secondary-text-color);cursor:help;vertical-align:middle}
      .snapshot-day,.snapshot-revision{padding:11px 13px;border:1px solid var(--divider-color);border-radius:9px;margin:8px 0;background:var(--secondary-background-color)}
      .snapshot-revision{margin:11px 0;background:var(--card-background-color)}.snapshot-day summary,.snapshot-revision summary{cursor:pointer;font-weight:550}
      .history-fields{display:grid;gap:6px;margin:12px 0}.history-field{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;padding:8px;border-bottom:1px solid var(--divider-color);font-size:12px}
      .history-field>span{color:var(--secondary-text-color)}.history-field>strong{font-weight:500;text-align:right;overflow-wrap:anywhere}
      .history-controls{display:flex;gap:18px;align-items:end;flex-wrap:wrap;margin:17px 0}
      .history-controls label{display:flex;flex-direction:column;gap:7px;font-size:12px;color:var(--secondary-text-color)}
      .history-select{background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:9px;color:var(--primary-text-color);padding:10px 14px;min-width:165px;font:inherit}
      .optical-history-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;margin:17px 0}
      .optical-history-tile{min-width:0;border:1px solid var(--divider-color);background:var(--secondary-background-color);border-radius:12px;padding:16px}
      .optical-history-tile h4{margin:0 0 12px}
      .optical-history-tile svg{display:block;width:100%;height:auto}
      .optical-history-summary{display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap;font-size:11px;color:var(--secondary-text-color)}
      .optical-history-summary b{display:block;color:var(--primary-text-color);font-size:13px;margin-top:3px}
      .optical-history-tile>small{display:block;color:var(--secondary-text-color);margin-top:9px}
      .temperature-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:15px 0}
      .temperature-summary>div{padding:14px 16px;border:1px solid var(--divider-color);border-radius:10px;background:var(--secondary-background-color)}
      .temperature-summary small{display:block;color:var(--secondary-text-color);margin-bottom:8px}
      .temperature-summary strong{font-size:22px}
      .temperature-chart{width:100%;overflow:hidden;margin:14px 0}
      .temperature-chart svg{display:block;width:100%;height:auto;max-height:300px}
      .temp-legend{display:flex;gap:15px;flex-wrap:wrap;color:var(--secondary-text-color);font-size:12px}
      .volume-strip{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:15px 0}
      .volume-strip>div{padding:16px 18px;background:var(--secondary-background-color);border-radius:10px;border:1px solid var(--divider-color)}
      .volume-strip small{display:block;color:var(--secondary-text-color);margin-bottom:8px}
      .volume-strip strong{font-size:22px;font-weight:650}
      .daily-bars{display:flex;gap:4px;align-items:flex-end;overflow-x:auto;min-height:158px;padding:12px 0;border-bottom:1px solid var(--divider-color)}
      .daily-bar-day{min-width:27px;flex:1;text-align:center;font-size:9px;color:var(--secondary-text-color)}
      .bar-pair{height:112px;display:flex;gap:2px;align-items:end;justify-content:center}
      .bar-pair i{display:block;width:36%;border-radius:3px 3px 0 0}.bar-rx{background:#29ade3}.bar-tx{background:#49bf87}
      .daily-bar-day small{font-size:9px}
      .port-selector{display:flex;gap:7px;flex-wrap:wrap;margin:16px 0 20px}
      .port-select{padding:8px 13px;border:1px solid var(--divider-color);border-radius:9px;background:var(--secondary-background-color);font-size:12px;color:var(--primary-text-color)}
      .port-select.selected{border-color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 13%,var(--card-background-color));color:var(--primary-color)}
      .event-list{display:grid;gap:8px}.event-item{display:flex;align-items:center;gap:12px;padding:12px 14px;background:var(--secondary-background-color);border:1px solid var(--divider-color);border-radius:9px;font-size:12px}.event-item time{margin-left:auto;color:var(--secondary-text-color);font-variant-numeric:tabular-nums}.event-dot{width:9px;height:9px;border-radius:50%;background:var(--primary-color);flex-shrink:0}.system-date{font-size:14px!important}
      .inventory-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:22px}.inventory-stats>div{background:var(--secondary-background-color);border-radius:12px;padding:17px}.inventory-stats small{display:block;color:var(--secondary-text-color);font-size:12px;margin-bottom:10px}.inventory-stats strong{display:block;font-size:20px;overflow-wrap:anywhere}
      .overview-macs{margin-left:auto;font-size:11px;color:var(--secondary-text-color)}
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
      /* Override pixel-sized legacy rules inside Shadow DOM at the end of CSS. */
      h1{font-size:${24*fontScale}px!important}
      h2{font-size:${19*fontScale}px!important}
      h3{font-size:${15*fontScale}px!important}
      button,input,select,label,td,th,summary,small,.muted,.section-subtitle,.footnote{font-size:${12*fontScale}px!important}
      .metric strong{font-size:${24*fontScale}px!important}
    </style><main class="${compact?'compact-view':''}"><header><div class="brand-wrap"><h1 class="brand"><img src="/ha_oraco_static/brand/icon.svg" alt="" aria-hidden="true"/> HoraInfo</h1><div class="brand-subtitle">${this.escape(switches.length===1?(switches[0].device?.name||switches[0].device?.model||switches[0].host):switches.length+" equipamentos monitorados")}</div></div><div class="header-actions"><label class="scale-picker">Tamanho do texto<select data-font-scale="true" aria-label="Escala da interface">${[0.9,1,1.1,1.2,1.35].map(n=>'<option value="'+n+'" '+(fontScale===n?'selected':'')+'>'+Math.round(n*100)+'%</option>').join('')}</select></label><button class="refresh" data-compact-toggle="true">${compact?'Exibição normal':'Exibição compacta'}</button><button class="refresh" id="refresh">Atualizar</button></div></header>
    <nav>${tabs.map(([id,label])=>'<button data-tab="'+id+'" class="'+(id===this.tab?"selected":"")+'">'+label+'</button>').join("")}</nav>
    ${body}</main>${this.snapshotDialog()}${this.portDialog()}`;
    this.shadowRoot.querySelectorAll("[data-edit-manual]").forEach(btn=>btn.addEventListener("click",event=>{
      event.stopPropagation();
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.editManual);
      const id=btn.dataset.manualId,entry=sw?.preferences?.infrastructure?.[id];
      if(!entry)return;
      const input=prompt("MACs associados a este equipamento, separados por vírgula. Relação documental, não descoberta física:",(entry.macs||[]).join(", "));
      if(input===null)return;
      const macs=[...new Set(input.split(",").map(x=>x.trim().toUpperCase()).filter(Boolean))];
      if(macs.length>50||macs.some(mac=>!/^[0-9A-F]{2}(:[0-9A-F]{2}){5}$/.test(mac))){
        this.error="Informe no máximo 50 MACs completos no formato AA:BB:CC:DD:EE:FF.";this.render();return;
      }
      this.savePreference(sw,"infrastructure",id,{...entry,macs});
    }));
    this.shadowRoot.querySelectorAll("[data-remove-manual]").forEach(btn=>btn.addEventListener("click",event=>{
      event.stopPropagation();
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.removeManual);
      if(sw&&confirm("Remover este equipamento informado manualmente?"))
        this.savePreference(sw,"infrastructure",btn.dataset.manualId,null);
    }));
    this.shadowRoot.querySelectorAll("[data-add-manual]").forEach(btn=>btn.addEventListener("click",async()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.addManual);
      if(!sw)return;
      const name=prompt("Nome do equipamento de infraestrutura:", "");
      if(!name||!name.trim())return;
      const port=prompt("Porta associada (informação manual, não detectada fisicamente):","");
      if(!port||!Object.hasOwn(sw.ports||{},port.trim())){this.error="Informe uma porta existente.";this.render();return;}
      const id="n"+Date.now().toString(36);
      await this.savePreference(sw,"infrastructure",id,{name:name.trim().slice(0,80),port:port.trim(),macs:[]});
    }));
    this.shadowRoot.querySelectorAll("[data-board-node]").forEach(node=>{
      node.addEventListener("pointerdown",event=>{
        if(event.button!==0||event.target.closest("[data-remove-manual], [data-edit-manual]"))return;
        const board=node.closest("[data-board]");
        const rect=board.getBoundingClientRect();
        const origin={x:event.clientX,y:event.clientY,left:parseFloat(node.style.left),top:parseFloat(node.style.top)};
        node.setPointerCapture(event.pointerId);
        const move=e=>{
          const x=Math.max(0,Math.min(88,origin.left+(e.clientX-origin.x)/rect.width*100));
          const y=Math.max(4,Math.min(96,origin.top+(e.clientY-origin.y)/rect.height*100));
          node.style.left=x+"%";node.style.top=y+"%";
          const id=node.dataset.boardNode,lines=board.querySelectorAll("[data-wire-from]");
          for(const line of lines){
            const from=line.dataset.wireFrom,to=line.dataset.wireTo;
            if(from===id){line.setAttribute("x1",(x+6)*10);line.setAttribute("y1",y*10);}
            if(to===id){line.setAttribute("x2",(x+6)*10);line.setAttribute("y2",y*10);}
          }
        };
        const up=()=>{
          node.removeEventListener("pointermove",move);
          node.removeEventListener("pointerup",up);
          const sw=(this.data?.switches||[]).find(x=>x.id===node.dataset.boardSwitch);
          if(sw&&((Math.abs(parseFloat(node.style.left)-origin.left)>0.2)||(Math.abs(parseFloat(node.style.top)-origin.top)>0.2)))
            this.savePreference(sw,"layout",node.dataset.boardKey,
              {x:Math.round(parseFloat(node.style.left)*10)/10,y:Math.round(parseFloat(node.style.top)*10)/10});
        };
        node.addEventListener("pointermove",move);
        node.addEventListener("pointerup",up);
        node.addEventListener("pointercancel",up);
      });
    });
    this.shadowRoot.querySelectorAll("[data-reset-board]").forEach(btn=>btn.addEventListener("click",async()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.resetBoard);
      if(!sw)return;
      const layout=sw.preferences?.layout||{};
      for(const [key] of Object.entries(layout))await this.savePreference(sw,"layout",key,null);
    }));
    this.shadowRoot.querySelectorAll("[data-sfp-limit-switch]").forEach(btn=>btn.addEventListener("click",()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.sfpLimitSwitch);
      if(sw)this.setOpticalLimits(sw,btn.dataset.sfpLimitMetric);
    }));
    this.shadowRoot.querySelectorAll("[data-open-port]").forEach(el=>el.addEventListener("click",()=>{
      this.portModal={switchId:el.dataset.openPort,number:el.dataset.portNumber};this.render();
      const id=el.dataset.openPort,port=el.dataset.portNumber;
      const sw=(this.data?.switches||[]).find(x=>x.id===id);
      this.fetchHistory(id,"traffic",port,this.chartHours[id+"|"+port]||this.defaultRange(sw||{preferences:{}}));
      if(!this.historyViews[id+"|daily|"+port+"|24|sfp"])this.fetchHistory(id,"daily",port);
    }));
    this.shadowRoot.querySelectorAll("[data-close-port]").forEach(btn=>btn.addEventListener("click",()=>{
      this.portModal=null;this.render();
    }));
    this.shadowRoot.querySelectorAll("[data-port-history]").forEach(btn=>btn.addEventListener("click",()=>{
      const sw=btn.dataset.portHistory,n=btn.dataset.portNumber;
      this.portModal=null;this.selectedPort[sw]=n;this.tab="history";this.render();this.loadCurrentCharts();
    }));
    this.shadowRoot.querySelectorAll("[data-rename-port]").forEach(btn=>btn.addEventListener("click",()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.renamePort);
      if(sw)this.askName(sw,"ports",btn.dataset.number,this.pref(sw,"ports",btn.dataset.number,""));
    }));
    this.shadowRoot.querySelectorAll("[data-tab]").forEach(el => el.addEventListener("click", () => {this.tab=el.dataset.tab;this.render();this.loadCurrentCharts();this.loadSfpTemperature();this.loadSfpOptics();this.loadStorageStats()}));
    this.shadowRoot.querySelectorAll("[data-traffic-port]").forEach(btn=>btn.addEventListener("click",()=>{
      this.selectedPort[btn.dataset.switch]=btn.dataset.trafficPort;
      const id=btn.dataset.switch,port=btn.dataset.trafficPort;
      this.fetchHistory(id,"traffic",port,this.chartHours[id+"|"+port]||this.defaultRange((this.data?.switches||[]).find(x=>x.id===id)||{preferences:{}}));
      if(!this.historyViews[id+"|daily|"+port+"|24|sfp"])this.fetchHistory(id,"daily",port);
    }));
    this.shadowRoot.querySelectorAll("[data-sfp-optical-hours]").forEach(select=>select.addEventListener("change",()=>{
      const id=select.dataset.sfpOpticalHours,hours=Number(select.value);
      this.sfpOpticalHours[id]=hours;
      this.render();
      this.loadSfpOptics();
    }));
    this.shadowRoot.querySelectorAll("[data-sfp-temp-hours]").forEach(select=>select.addEventListener("change",()=>{
      const id=select.dataset.sfpTempHours,hours=Number(select.value);
      this.sfpTemperatureHours[id]=hours;
      this.fetchHistory(id,"sfp_temperature","__total__",hours);
    }));
    this.shadowRoot.querySelectorAll("[data-chart-hours-select]").forEach(btn=>btn.addEventListener("change",()=>{
      const id=btn.dataset.chartHoursSelect,port=btn.dataset.port,hours=Number(btn.value);
      this.chartHours[id+"|"+port]=hours;
      const sw=(this.data?.switches||[]).find(x=>x.id===id);
      if(sw)this.savePreference(sw,"options","default_hours",hours);
      this.fetchHistory(id,"traffic",port,hours);
    }));
    this.shadowRoot.querySelectorAll("[data-daily-switch]").forEach(btn=>btn.addEventListener("click",()=>this.fetchHistory(btn.dataset.dailySwitch,"daily",btn.dataset.dailyPort)));
    this.shadowRoot.querySelectorAll("[data-snapshot-switch]").forEach(btn=>btn.addEventListener("click",()=>{
      this.snapshotModal={switchId:btn.dataset.snapshotSwitch,kind:btn.dataset.snapshotKind,label:btn.dataset.snapshotLabel};
      this.snapshotDay=null;
      this.fetchHistory(btn.dataset.snapshotSwitch,"snapshots","__total__",24,btn.dataset.snapshotKind);
    }));
    this.shadowRoot.querySelectorAll("[data-retry-snapshot]").forEach(btn=>btn.addEventListener("click",()=>{
      if(this.snapshotModal)this.fetchHistory(this.snapshotModal.switchId,"snapshots","__total__",24,this.snapshotModal.kind);
    }));
    this.shadowRoot.querySelectorAll("[data-close-audit]").forEach(btn=>btn.addEventListener("click",()=>{
      this.snapshotModal=null;this.render();
    }));
    this.shadowRoot.querySelectorAll("[data-audit-day]").forEach(btn=>btn.addEventListener("click",()=>{
      this.snapshotDay=btn.dataset.auditDay;this.render();
    }));
    this.shadowRoot.querySelectorAll("[data-modal-backdrop]").forEach(el=>el.addEventListener("click",e=>{
      if(e.target===el){this.snapshotModal=null;this.portModal=null;this.render();}
    }));
    this.shadowRoot.querySelectorAll("[data-history-port]").forEach(el=>el.addEventListener("change",()=>{
      this.selectedPort[el.dataset.historyPort]=el.value;
      this.render();
      this.loadCurrentCharts();
    }));
    this.shadowRoot.querySelectorAll("[data-name-mac]").forEach(btn=>btn.addEventListener("click",()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===btn.dataset.nameMac);
      if(sw)this.askName(sw,"devices",btn.dataset.mac,this.pref(sw,"devices",btn.dataset.mac,""));
    }));
    this.shadowRoot.querySelectorAll("[data-ddmi-refresh]").forEach(el=>el.addEventListener("click",()=>this.refreshDdmi(el.dataset.ddmiRefresh)));
    this.shadowRoot.querySelectorAll("[data-endpoint-select]").forEach(el=>el.addEventListener("change",()=>{
      this.endpointSelection[el.dataset.endpointSelect]=el.value;this.render();
    }));
    this.shadowRoot.querySelectorAll("[data-font-scale]").forEach(el=>el.addEventListener("change",()=>{
      const sw=(this.data?.switches||[])[0];
      if(sw)this.savePreference(sw,"options","font_scale",Number(el.value));
    }));
    this.shadowRoot.querySelectorAll("[data-mac-setting]").forEach(el=>el.addEventListener("change",()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===el.dataset.switchId);
      if(!sw)return;
      const key=el.dataset.macSetting;
      const value=["page_size","height"].includes(key)?Number(el.value):el.value;
      const view={...this.macSettings(sw),[key]:value};
      this.macPages[sw.id]=1;
      this.savePreference(sw,"options","mac_view",view);
    }));
    this.shadowRoot.querySelectorAll("[data-mac-page]").forEach(el=>el.addEventListener("click",()=>{
      const page=Number(el.dataset.page);
      if(Number.isInteger(page)&&page>=1&&page<=8){
        this.macPages[el.dataset.macPage]=page;this.render();
      }
    }));
    this.shadowRoot.querySelectorAll("[data-mac-reset]").forEach(el=>el.addEventListener("click",()=>{
      const sw=(this.data?.switches||[]).find(x=>x.id===el.dataset.macReset);
      if(!sw)return;
      this.macPages[sw.id]=1;
      this.savePreference(sw,"options","mac_view",{query:"",port:"all",vlan:"all",vendor:"all",page_size:50,height:440});
    }));
    this.shadowRoot.querySelectorAll("[data-compact-toggle]").forEach(btn=>btn.addEventListener("click",()=>{
      const sw=(this.data?.switches||[])[0];
      if(sw)this.savePreference(sw,"options","compact",!this.pref(sw,"options","compact",false));
    }));
    this.shadowRoot.querySelectorAll("[data-retry-history]").forEach(btn=>btn.addEventListener("click",()=>this.fetchHistory(btn.dataset.retryHistory,"traffic",btn.dataset.retryPort,Number(btn.dataset.retryHours))));
    this.shadowRoot.querySelectorAll("[data-refresh-storage]").forEach(btn=>btn.addEventListener("click",()=>this.fetchHistory(btn.dataset.refreshStorage,"storage")));
    this.shadowRoot.getElementById("refresh")?.addEventListener("click",()=>this.refresh());

  }
}
customElements.define("ha-oraco-panel",HaOracoPanel);
