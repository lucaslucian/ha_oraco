"use strict";
// Standalone Node smoke test: execute every dashboard tab and modal with
// realistic payloads. No browser, network, switch or Home Assistant required.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
let Panel;
const root=()=>{
  const shadow={innerHTML:"",querySelectorAll:()=>[],getElementById:()=>null};
  return shadow;
};
const context={
  HTMLElement:class { attachShadow(){this.shadowRoot=root();} },
  customElements:{define(_name,ctor){Panel=ctor;}},
  console,Date,Number,String,Object,Array,Math,JSON,Set,Map,
  prompt:()=>null,confirm:()=>false
};
const src=fs.readFileSync(path.join(__dirname,"../custom_components/ha_oraco/frontend/ha-oraco-panel.js"),"utf8");
vm.runInNewContext(src,context,{filename:"ha-oraco-panel.js"});
assert.equal(typeof Panel,"function");
const panel=new Panel();
const sw={
  id:"test-switch",host:"10.0.0.254",device:{model:"HC-SWTGW218AS",firmware:"V200.2.4",name:"Lab Switch"},
  ports:{"1":{port:"1",up:true,speed:"1000M",duplex:"Full",rx_bps:100000,
      tx_bps:80000,rx_bytes:300000,tx_bytes:600000,rx_packets:1000,tx_packets:2000},
      "2":{port:"2",up:false,speed:"Auto",rx_bps:null,tx_bps:null}},
  preferences:{ports:{"1":"Uplink"},devices:{"E8:4C:4A:21:A8:5D":"AP"}},
  mac:{mac_current:1,mac_known:1,mac_entries:[{mac:"E8:4C:4A:21:A8:5D",port:"1",vlan:"1",vendor:"Test Vendor"}]},
  sfp:{sfp:{module_present:"Yes",temperature_c:65.25,voltage_v:3.12,current_ma:0,
            rx_dbm:-40,tx_dbm:-18,vendor:"ODI"}},
  topology:{nodes:[{id:"switch",kind:"switch",label:"Lab Switch"},
                   {id:"port:1",kind:"port",label:"Porta 1"},
                   {id:"mac:E8:4C:4A:21:A8:5D|1",kind:"learned_mac",mac:"E8:4C:4A:21:A8:5D",vendor:"Test Vendor",label:"Test Vendor"}],
             edges:[{from:"switch",to:"port:1"},{from:"port:1",to:"mac:E8:4C:4A:21:A8:5D|1"}]},
  network:{},diagnostics:{endpoints:{}},oui:{prefix_count:40316,sources:{}},
  peaks:{total:{rx_bps:200000,tx_bps:100000},ports:{"1":{rx_bps:100000,tx_bps:90000}}},
  traffic_history:[],traffic_by_port:{},recent_changes:[]
};
panel.data={switches:[sw]};
for(const tab of ["overview","ports","history","sfp","mac","vlan","protection","topology","system"]){
  panel.tab=tab;
  assert.doesNotThrow(()=>panel.render(),"Rendering tab "+tab);
  assert.ok(panel.shadowRoot.innerHTML.includes("HoraInfo"));
}
panel.tab="ports";
panel.portModal={switchId:sw.id,number:"1"};
assert.doesNotThrow(()=>panel.render(),"Port modal");
panel.portModal=null;
panel.snapshotModal={switchId:sw.id,kind:"isolation",label:"Isolamento"};
panel.historyViews[sw.id+"|snapshots|__total__|24|isolation"]={
  loading:false,items:[{day:"2026-10-15",checks:8,changes:1,
    checked_at:"2026-10-15T10:00:00Z",events:[{
      timestamp:"2026-10-15T09:00:00Z",data:{ports:[{port:1,state:"Forwarding"}]}
    }]}]
};
assert.doesNotThrow(()=>panel.render(),"Snapshot modal with nested arrays");
assert.ok(!panel.shadowRoot.innerHTML.includes("[object Object]"));
assert.match(panel.readableError({code:"not_found",message:"History unavailable"}),/History unavailable/);
(async()=>{
  panel._hass={connection:{sendMessagePromise:async request=>{
    if(request.mode==="traffic")return {items:[{timestamp:"2026-10-15T10:00:00Z",rx:100,tx:250}],total:{rx_bytes:500,tx_bytes:600}};
    if(request.mode==="sfp_optical")return {items:[],count:0};
    return {items:[]};
  }}};
  await panel.fetchHistory(sw.id,"traffic");
  assert.equal(panel.historyViews[sw.id+"|traffic|__total__|24|sfp"].items.length,1);
  // Signed optical power limits must work in either order.
  const originalPrompt=context.prompt;
  const originalSave=panel.savePreference.bind(panel);
  const saved=[];
  panel.savePreference=async (_sw,category,key,value)=>saved.push({category,key,value});
  for(const values of [["-15","-25"],["-25","-15"],["−15,5","−25,5"]]){
    let index=0;
    context.prompt=()=>values[index++];
    await panel.setOpticalLimits(sw,"rx_dbm");
    const latest=saved.at(-1);
    assert.equal(latest.category,"thresholds");
    assert.equal(latest.key,"rx_dbm");
    assert.ok(latest.value.low<latest.value.high);
  }
  assert.deepEqual(saved[0].value,{low:-25,high:-15});
  assert.deepEqual(saved[2].value,{low:-25.5,high:-15.5});
  context.prompt=originalPrompt;
  panel.savePreference=originalSave;
  console.log("Frontend runtime smoke tests passed");
})().catch(err=>{console.error(err);process.exitCode=1;});
