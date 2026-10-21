'use strict';
(() => {
  const root=document.querySelector('#ping-app'),$=s=>root.querySelector(s),csrf=root.dataset.csrf;
  let devices=[],busy=false,initialDevice=Number(root.dataset.device)||null;
  const error=e=>{const box=$('#ping-error');box.hidden=!e;box.textContent=e?String(e.message||e):'';};
  const fmt=v=>Number(v).toLocaleString('cs-CZ',{maximumFractionDigits:2});
  async function api(path,data,method='POST'){
    const options=data===undefined?{}:{method,headers:{'X-CSRF-Token':csrf},body:data instanceof FormData?data:JSON.stringify(data)};
    if(data!==undefined&&!(data instanceof FormData))options.headers['Content-Type']='application/json';
    const response=await fetch('/ping/api/'+path,options);
    if(response.redirected){location.href=response.url;throw Error('Přihlaste se znovu');}
    const result=await response.json();if(!response.ok)throw Error(result.error||'Požadavek selhal');return result;
  }
  function element(tag,text,parent){const node=document.createElement(tag);if(text!=null)node.textContent=text;if(parent)parent.append(node);return node;}
  function button(parent,text,action){const b=element('button',text,parent);b.type='button';if(text==='Odstranit')b.className='pa-delete';b.onclick=()=>Promise.resolve().then(action).catch(error);return b;}
  function edit(d){$('[data-editor-title]').textContent='Upravit zařízení · '+d.name;const form=$('#ping-device-form');for(const input of form.elements)if(input.name){const v=d[input.name];input.value=input.type==='datetime-local'?(v?new Date(v*1000-new Date(v*1000).getTimezoneOffset()*60000).toISOString().slice(0,16):''):(v??'');}$('#ping-editor').open=true;form.scrollIntoView({behavior:'smooth'});}
  function renderTable(){
    const body=$('#ping-devices');body.replaceChildren();const group=$('#ping-group').value,list=devices.filter(d=>!group||d.group_name===group);
    $('#ping-device-count').textContent=list.length+' zařízení';
    for(const d of list){
      const row=element('tr',null,body),name=element('td',null,row);element('strong',d.name,name);if(d.description)element('small',d.description,name);
      element('td',d.address,row).className='pa-address';const groupCell=element('td',d.group_name||'Bez skupiny',row);groupCell.className='pa-cell-muted';if(d.tags)element('small',d.tags,groupCell);const measure=element('td',fmt(d.interval)+' s',row);element('small',d.probes+' sond'+(d.probes===1?'a':d.probes<5?'y':''),measure);
      element('span',d.paused?'Pozastaveno':d.maintenance_start<=Date.now()/1000&&d.maintenance_until>Date.now()/1000?'Údržba':'Aktivní',element('td',null,row)).className='pa-state'+(d.paused?' pa-paused':'');
      const actions=element('div',null,element('td',null,row));actions.className='pa-row-actions';button(actions,'Upravit',()=>edit(d));
      button(actions,d.paused?'Obnovit':'Pozastavit',async()=>{await api('devices/'+d.id,{paused:d.paused?0:1});await refresh();});
      button(actions,d.maintenance_until>Date.now()/1000?'Ukončit údržbu':'Údržba 1 h',async()=>{await api('devices/'+d.id,{maintenance_start:0,maintenance_until:d.maintenance_until>Date.now()/1000?0:Date.now()/1000+3600});await refresh();});
      button(actions,'Odstranit',async()=>{if(!confirm('Odstranit '+d.name+' včetně celé historie?'))return;await api('devices/'+d.id,{},'DELETE');await refresh();});
    }
    if(!list.length)element('td','Zatím žádná zařízení v této skupině.',element('tr',null,body)).colSpan=6;
  }
  async function refresh(){
    if(busy)return;busy=true;
    try{const data=await api('devices');devices=data.devices;$('#ping-enabled').checked=data.enabled;$('#ping-health').dataset.state=data.enabled?(data.healthy?'on':'error'):'off';$('#ping-health').textContent=data.enabled?(data.healthy?'Sběr běží':'Služba neodpovídá'):'Sběr vypnutý';
      const group=$('#ping-group'),value=group.value;group.replaceChildren(element('option','Všechny'));group.firstChild.value='';for(const g of [...new Set(devices.map(d=>d.group_name))].filter(Boolean).sort()){const o=element('option',g,group);o.value=g;}group.value=[...group.options].some(o=>o.value===value)?value:'';
      renderTable();if(initialDevice){const d=devices.find(d=>d.id===initialDevice);initialDevice=null;if(d)edit(d);}error(null);
    }catch(e){error(e);}finally{busy=false;}
  }
  $('#ping-enabled').onchange=async e=>{try{await api('settings',{enabled:e.target.checked});await refresh();}catch(err){e.target.checked=!e.target.checked;error(err);}};
  $('#ping-group').onchange=renderTable;
  function newDevice(){const form=$('#ping-device-form');form.reset();form.elements.id.value='';$('[data-editor-title]').textContent='Nové zařízení';$('#ping-editor').open=true;form.scrollIntoView({behavior:'smooth'});}
  $('#ping-new').onclick=newDevice;$('#ping-add').onclick=newDevice;
  $('#ping-device-form').onsubmit=async e=>{e.preventDefault();try{const data=Object.fromEntries(new FormData(e.target)),id=data.id;delete data.id;for(const k of ['maintenance_start','maintenance_until'])data[k]=data[k]?new Date(data[k]).getTime()/1000:0;if(data.maintenance_until&&data.maintenance_until<=data.maintenance_start)throw Error('Konec údržby musí být po začátku');await api('devices'+(id?'/'+id:''),data);e.target.reset();e.target.elements.id.value='';$('[data-editor-title]').textContent='Nové zařízení';await refresh();}catch(err){error(err);}};
  $('#ping-import').onsubmit=async e=>{e.preventDefault();try{await api('csv',new FormData(e.target));await refresh();}catch(err){error(err);}};
  // Accessible hover/focus help, with a click toggle for touch screens.
  let activeHelp=null,helpTimer=null;
  function hideHelp(){clearTimeout(helpTimer);if(!activeHelp)return;document.getElementById(activeHelp.dataset.help).hidden=true;activeHelp.setAttribute('aria-expanded','false');activeHelp=null;}
  function positionHelp(){if(!activeHelp)return;const tip=document.getElementById(activeHelp.dataset.help),button=activeHelp.getBoundingClientRect(),width=document.documentElement.clientWidth;tip.style.maxWidth=Math.max(0,width-24)+'px';const box=tip.getBoundingClientRect();tip.style.left=Math.min(Math.max(12,button.left),Math.max(12,width-box.width-12))+'px';const below=button.bottom+9;tip.style.top=(below+box.height<=innerHeight-12?below:Math.max(12,button.top-box.height-9))+'px';}
  function showHelp(button){clearTimeout(helpTimer);if(activeHelp!==button)hideHelp();activeHelp=button;const tip=document.getElementById(button.dataset.help);tip.hidden=false;button.setAttribute('aria-expanded','true');positionHelp();}
  function delayHide(){clearTimeout(helpTimer);helpTimer=setTimeout(()=>{if(activeHelp&&document.activeElement!==activeHelp)hideHelp();},140);}
  root.querySelectorAll('.pa-help').forEach(button=>{const tip=document.getElementById(button.dataset.help);let openOnPointerDown=false;
    button.addEventListener('mouseenter',()=>showHelp(button));button.addEventListener('mouseleave',delayHide);button.addEventListener('focus',()=>showHelp(button));button.addEventListener('blur',()=>{helpTimer=setTimeout(hideHelp,140);});
    button.addEventListener('pointerdown',()=>{openOnPointerDown=button.getAttribute('aria-expanded')==='true';});
    button.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();if(event.detail===0||!openOnPointerDown)showHelp(button);else hideHelp();});
    tip.addEventListener('mouseenter',()=>clearTimeout(helpTimer));tip.addEventListener('mouseleave',delayHide);
  });
  document.addEventListener('pointerdown',event=>{if(activeHelp&&!activeHelp.contains(event.target)&&!document.getElementById(activeHelp.dataset.help).contains(event.target))hideHelp();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')hideHelp();});window.addEventListener('resize',positionHelp);window.addEventListener('scroll',positionHelp,true);
  setInterval(()=>{if(!document.hidden)refresh();},10000);refresh();
})();
