'use strict';
(() => {
const root=document.querySelector('[data-ping-overview]');if(!root)return;
const $=s=>root.querySelector(s),fmt=(v,u='')=>v==null?'—':Number(v).toLocaleString('cs-CZ',{maximumFractionDigits:2})+u;
const labels={UP:'Dostupné',DOWN:'Nedostupné',DEGRADED:'Zhoršená odezva',UNKNOWN:'Neznámý stav',PAUSED:'Pozastaveno'};
const el=(tag,text,parent)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(parent)parent.append(n);return n;};
function sparkline(tile,buckets){
  const points=buckets.flatMap(b=>b.unknowns||b.losses?[null]:[[b.min_ts,b.min_rtt],[b.max_ts,b.max_rtt]].filter(p=>p[1]!=null).sort((a,b)=>a[0]-b[0]));const measured=points.filter(Boolean);if(!measured.length)return;
  const lo=Math.min(...measured.map(p=>p[1])),hi=Math.max(...measured.map(p=>p[1])),start=measured[0][0],end=measured.at(-1)[0];
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 200 80');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
  const make=tag=>document.createElementNS(svg.namespaceURI,tag),defs=make('defs'),gradient=make('linearGradient'),gradientId='pm-fill-'+tile.dataset.deviceId;
  gradient.id=gradientId;gradient.setAttribute('x1','0');gradient.setAttribute('y1','0');gradient.setAttribute('x2','0');gradient.setAttribute('y2','1');gradient.setAttribute('gradientUnits','objectBoundingBox');
  for(const [offset,opacity] of [['0%','.62'],['100%','0']]){const stop=make('stop');stop.setAttribute('offset',offset);stop.setAttribute('stop-color','white');stop.setAttribute('stop-opacity',opacity);gradient.append(stop);}defs.append(gradient);svg.append(defs);
  let segments=[],segment=[];for(const p of points){if(!p){if(segment.length)segments.push(segment);segment=[];continue;}if(segment.length&&p[0]-segment.at(-1)[0]>100){segments.push(segment);segment=[];}segment.push(p);}if(segment.length)segments.push(segment);
  for(const segment of segments){const coords=segment.map(p=>[200*(p[0]-start)/Math.max(1,end-start),62-45*(p[1]-lo)/Math.max(.001,hi-lo)]),d=coords.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+','+p[1].toFixed(1)).join('');
    if(coords.length>1){const area=make('path');area.setAttribute('d',d+'L'+coords.at(-1)[0].toFixed(1)+',80L'+coords[0][0].toFixed(1)+',80Z');area.setAttribute('fill','url(#'+gradientId+')');svg.append(area);}
    const line=make('path');line.setAttribute('d',d);line.setAttribute('fill','none');line.setAttribute('stroke','white');line.setAttribute('stroke-opacity','.55');line.setAttribute('stroke-width','2');svg.append(line);
  }
  tile.append(svg);
}
function render(data){
  root.hidden=!data.enabled;if(!data.enabled){$('[data-pm-tiles]').replaceChildren();$('[data-pm-rankings]').replaceChildren();return;}
  $('[data-pm-health]').textContent=data.healthy?'● Živý přehled':'● Sběrač neodpovídá';
  const tiles=$('[data-pm-tiles]');tiles.replaceChildren();
  for(const d of data.devices){const tile=el('a',null,tiles);tile.href='/ping/view/'+d.id;tile.dataset.deviceId=d.id;tile.className='pm-tile pm-'+d.state.toLowerCase();tile.setAttribute('aria-label',`${d.name}: ${labels[d.state]}, ${fmt(d.rtt,' ms')}. Otevřít grafy.`);el('span',d.name,tile).className='pm-tile-name';const value=el('strong',d.state==='DOWN'?'Offline':d.state==='PAUSED'?'Pauza':d.state==='UNKNOWN'?'—':fmt(d.rtt),tile);value.className='pm-tile-value';if(['UP','DEGRADED'].includes(d.state))el('small','ms',value);const footer=el('span',null,tile);footer.className='pm-tile-footer';el('span',labels[d.state],footer);el('span','Detail ↗',footer);sparkline(tile,d.sparkline);}
  if(!data.devices.length)el('p','Zatím nejsou přidána žádná zařízení.',tiles).className='pm-empty';
  const rankings=$('[data-pm-rankings]');rankings.replaceChildren();
  for(const [title,icon,key,unit,label] of [['Nejpomalejší odezva','↗','max_rtt',' ms','MAX RTT'],['Nejvíce výpadků','⌁','incidents','','Incidenty'],['Nejvyšší ztrátovost','◌','loss',' %','Ztráty']]){
    const card=el('section',null,rankings);card.className='pm-ranking';const heading=el('h4',null,card);el('span',icon,heading).setAttribute('aria-hidden','true');heading.append(document.createTextNode(title));
    const list=data.devices.filter(d=>d.stats[key]!=null&&(key!=='incidents'||d.stats[key]>0)).sort((a,b)=>b.stats[key]-a.stats[key]).slice(0,5);
    if(!list.length){el('p',key==='incidents'?'Žádné výpadky v tomto období.':'Pro toto období nejsou naměřená data.',card).className='pm-empty';continue;}
    const table=el('table',null,card),head=el('tr',null,el('thead',null,table));el('th','Zařízení',head);el('th',label,head);const body=el('tbody',null,table);
    list.forEach((d,i)=>{const row=el('tr',null,body),name=el('td',null,row);el('span',String(i+1).padStart(2,'0'),name).className='pm-rank-number';el('a',d.name,name).href='/ping/view/'+d.id;el('td',fmt(d.stats[key],unit),row);});
  }
  $('[data-pm-updated]').textContent='Aktualizováno '+new Date().toLocaleTimeString('cs-CZ')+' · automaticky každých 15 s';
}
let busy=false;
async function refresh(){if(busy||document.hidden)return;busy=true;try{const response=await fetch('/ping/public/summary?period='+$('[data-pm-period]').value,{cache:'no-store'});if(!response.ok)throw Error();render(await response.json());}catch{root.hidden=true;}finally{busy=false;}}
$('[data-pm-period]').onchange=refresh;document.addEventListener('visibilitychange',refresh);setInterval(refresh,15000);refresh();
})();
