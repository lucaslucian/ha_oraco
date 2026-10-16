"use strict";
// Chromium smoke test for responsive, keyboard-accessible Shadow DOM views.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {chromium}=require("playwright");

(async()=>{
  const browser=await chromium.launch({headless:true});
  try{
    const source=fs.readFileSync(path.join(__dirname,"../custom_components/ha_oraco/frontend/ha-oraco-panel.js"),"utf8");
    const sizes=[360,390,768,1280,1600];
    for(const width of sizes){
      const page=await browser.newPage({viewport:{width,height:860}});
      await page.setContent('<ha-oraco-panel></ha-oraco-panel>');
      await page.addScriptTag({content:source});
      const metrics=await page.evaluate(()=>{
        const panel=document.querySelector("ha-oraco-panel");
        panel.data={switches:[{
          id:"test",host:"192.0.2.5",device:{name:"Switch teste",model:"OEM",firmware:"2"},
          ports:{"1":{port:"1",up:true,speed:"1G"}},preferences:{options:{font_scale:1.35}},
          mac:{mac_current:1,mac_known:1,mac_history_entries:[{mac:"00:11:22:33:44:55",vlan:"1",port:"1",vendor:"Fabricante Teste",first_seen:"2026-10-16T10:00:00Z",last_seen:"2026-10-16T10:01:00Z"}]},
          sfp:{sfp:{module_present:"Yes",vendor:"Test",temperature_c:23}},
          network:{dhcp:{enabled:true,per_port:{"1":{trusted:true}},trust_status_available:true},
                   igmp:{enabled:true,groups:[{ip:"239.1.1.1",vlan:"1",ports:"Port 1"}],per_port:{"1":[{group:"239.1.1.1",vlan:"1"}]}}},
          topology:{nodes:[],edges:[]},diagnostics:{endpoints:{}},peaks:{ports:{},total:{}},
          recent_changes:[],oui:{prefix_count:0},endpoint_catalog:[{key:"sfp",path:"/transceiver.cgi",interval_seconds:60,description:"Diagnóstico SFP+"}]
        }]};
        const details={};
        const titleScale=parseFloat(window.getComputedStyle(panel.shadowRoot.querySelector("h1")||panel.shadowRoot.host).fontSize);
        for(const tab of ["mac","endpoints","services","sfp"]){
          panel.tab=tab;panel.render();
          const root=panel.shadowRoot;
          details[tab]={
            visible:root.querySelector("main")?.getBoundingClientRect().width,
            tableScroll:!!root.querySelector(".mac-table-scroll"),
            status:root.querySelector("main")?.textContent?.includes("HoraInfo")
          };
          if(tab==="mac"){
            if(!root.querySelector(".mac-table-scroll"))throw new Error("MAC table absent");
          }
        }
        const modalPanel=panel;
        modalPanel.snapshotModal={switchId:"test",kind:"sfp",label:"SFP+"};
        modalPanel.render();
        const close=modalPanel.shadowRoot.querySelector("[data-close-audit]");
        const rect=close.getBoundingClientRect();
        return {fontPx:titleScale,bodyWidth:document.documentElement.scrollWidth,viewport:window.innerWidth,
                closeWidth:rect.width,closeHeight:rect.height,
                outlineClose:!!close.querySelector("svg"),details};
      });
      assert(metrics.fontPx>=30,"Accessible text scale not applied: "+metrics.fontPx);
      assert(metrics.bodyWidth<=metrics.viewport+3,
        "Horizontal page overflow at "+width+"px: "+JSON.stringify(metrics));
      assert(metrics.closeWidth>=36 && metrics.closeHeight>=36,
        "Close target too small at "+width+"px");
      assert(metrics.outlineClose,"Modal close icon absent");
      for(const tab of Object.values(metrics.details))assert(tab.status);
      await page.close();
    }
    process.stdout.write("Chromium responsive UI smoke passed (360/390/768/1280/1600px)\n");
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
