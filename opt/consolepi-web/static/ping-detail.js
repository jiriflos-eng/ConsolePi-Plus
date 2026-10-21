'use strict';
(() => {
const root=document.querySelector('[data-ping-detail]');if(!root)return;
const $=s=>root.querySelector(s),id=Number(root.dataset.pingDetail),fmt=(v,u='')=>v==null?'—':Number(v).toLocaleString('cs-CZ',{maximumFractionDigits:2})+u, date=t=>new Date(t*1000).toLocaleString('cs-CZ');
const el=(tag,text,parent)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(parent)parent.append(n);return n;};
const labels={UP:'Dostupné',DOWN:'Nedostupné',DEGRADED:'Zhoršená odezva',UNKNOWN:'Neznámý stav',PAUSED:'Pozastaveno'};
let period=3600,end=null,busy=false,history=null;
async function get(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw Error(r.status===404?'Zařízení není dostupné nebo je Ping Monitor vypnutý.':'Historii nelze načíst.');return r.json();}
function draw(canvas,metric){
 if(!history)return;
 const rect=canvas.getBoundingClientRect(),width=Math.max(250,rect.width),height=rect.height,ratio=Math.min(2,devicePixelRatio||1);canvas.width=width*ratio;canvas.height=height*ratio;
 const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);const styles=getComputedStyle(root),muted=styles.getPropertyValue('--muted').trim()||'#73878b',line=styles.getPropertyValue('--line').trim()||'#dbe4e6';
 const start=history.start,finish=history.end,left=48,right=18,top=18,bottom=34,plotW=width-left-right,plotH=height-top-bottom;
 const color=metric==='loss'?'#d19a31':metric==='jitter'?'#7e79c9':'#169e83';
 const points=history.buckets.flatMap(b=>(metric==='rtt'?b.points:(b[metric]!=null?[[b.first_ts,b[metric]]]:[])).map(p=>({ts:p[0],value:p[1],bucket:b})));
 const max=metric==='loss'?100:Math.max(.01,...points.map(p=>p.value))*1.15,x=t=>left+(t-start)/(finish-start)*plotW,y=v=>top+plotH-v/max*plotH;
 ctx.font='10px sans-serif';ctx.fillStyle=muted;ctx.strokeStyle=line;ctx.lineWidth=1;
 for(let n=0;n<=4;n++){const v=max*n/4,yy=y(v);ctx.beginPath();ctx.moveTo(left,yy);ctx.lineTo(width-right,yy);ctx.stroke();ctx.fillText(fmt(v),5,yy+3);}
 const ticks=width<480?2:4;for(let n=0;n<=ticks;n++){const ts=start+(finish-start)*n/ticks;const label=new Date(ts*1000).toLocaleString('cs-CZ',finish-start<=172800?{hour:'2-digit',minute:'2-digit'}:{day:'2-digit',month:'2-digit'});ctx.fillText(label,Math.min(width-60,Math.max(left,x(ts)-18)),height-11);}
 ctx.save();ctx.beginPath();ctx.rect(left,top,plotW,plotH);ctx.clip();
 for(const i of history.incidents){ctx.fillStyle='#d9576517';const a=Math.max(start,i.start),b=Math.min(finish,i.end||finish);ctx.fillRect(x(a),top,x(b)-x(a),plotH);}
 if(metric==='rtt')for(const b of history.buckets)if(b.losses){ctx.fillStyle='#d19a3199';ctx.fillRect(x(b.bucket),top,Math.max(3,plotW*history.bucket_size/(finish-start)),4);}
 const gradient=ctx.createLinearGradient(0,top,0,top+plotH);gradient.addColorStop(0,color+'26');gradient.addColorStop(1,color+'03');
 let previous=null;
 for(const p of points){const b=p.bucket,px=x(p.ts),py=y(p.value),gap=b.unknowns||(metric==='rtt'&&b.losses);
   if(previous&&!gap&&!previous.gap&&p.ts-previous.ts<=Math.max(history.bucket_size*1.6,65)){
     ctx.fillStyle=gradient;ctx.beginPath();ctx.moveTo(x(previous.ts),y(previous.value));ctx.lineTo(px,py);ctx.lineTo(px,y(0));ctx.lineTo(x(previous.ts),y(0));ctx.closePath();ctx.fill();
     ctx.strokeStyle=color;ctx.lineWidth=1.7;ctx.beginPath();ctx.moveTo(x(previous.ts),y(previous.value));ctx.lineTo(px,py);ctx.stroke();
   }
   ctx.fillStyle=color;ctx.beginPath();ctx.arc(px,py,finish-start>=172800?1.4:points.length>300?1.3:2.4,0,2*Math.PI);ctx.fill();previous={...p,gap};
 }
 if(metric==='rtt'&&history.resolution===86400){ctx.strokeStyle='#778b96';ctx.setLineDash([4,4]);let prev=null;for(const b of history.buckets){if(b.typical_rtt==null||b.unknowns||b.losses){prev=null;continue;}const p=[b.first_ts,b.typical_rtt];if(prev&&p[0]-prev[0]<Math.max(172800,history.bucket_size*1.6)){ctx.beginPath();ctx.moveTo(x(prev[0]),y(prev[1]));ctx.lineTo(x(p[0]),y(p[1]));ctx.stroke();}prev=p;}ctx.setLineDash([]);}
 ctx.restore();
 if(!points.length){ctx.fillStyle=muted;ctx.textAlign='center';ctx.fillText('V tomto období nejsou naměřená data',left+plotW/2,top+plotH/2);ctx.textAlign='left';}
 const base=ctx.getImageData(0,0,canvas.width,canvas.height);
 canvas.onpointermove=e=>{ctx.putImageData(base,0,0);const bounds=canvas.getBoundingClientRect(),mouse=(e.clientX-bounds.left)*width/bounds.width;let nearest=null,distance=Infinity;for(const p of points){const d=Math.abs(x(p.ts)-mouse);if(d<distance){nearest=p;distance=d;}}if(!nearest)return;ctx.strokeStyle=muted;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(x(nearest.ts),top);ctx.lineTo(x(nearest.ts),height-bottom);ctx.stroke();ctx.setLineDash([]);const message=date(nearest.ts)+' · '+fmt(nearest.value,metric==='loss'?' %':' ms')+' · ztráty '+nearest.bucket.losses+'/'+nearest.bucket.attempts;canvas.title=message;$('[data-pd-tooltip]').textContent=message;};
 canvas.onpointerleave=()=>ctx.putImageData(base,0,0);
}
function redraw(){draw($('[data-pd-latency]'),'rtt');draw($('[data-pd-loss]'),'loss');draw($('[data-pd-jitter]'),'jitter');}
async function refresh(){
 if(busy)return;busy=true;
 try{
 const query=new URLSearchParams({period,...(end?{end}:{})}),budget=period>=172800?Math.max(24,Math.min(96,Math.floor(root.clientWidth/10))):Math.max(100,Math.min(600,Math.floor(root.clientWidth))),[summary,data]=await Promise.all([get('/ping/public/summary?'+query),get('/ping/public/history/'+id+'?'+query+'&buckets='+budget)]),device=summary.devices.find(d=>d.id===id);
 if(!device)throw Error('Ping Monitor je vypnutý nebo zařízení bylo odstraněno.');history=data;
 $('[data-pd-name]').textContent=device.name;document.title=device.name+' · Ping Monitor · ConsolePi+';
 $('[data-pd-status]').textContent=labels[device.state]+' · poslední úspěch '+(device.last_ok?date(device.last_ok):'dosud nezměřeno');$('[data-pd-current]').textContent=['UP','DEGRADED'].includes(device.state)?fmt(device.rtt):device.state==='DOWN'?'Offline':'—';
 const stats=$('[data-pd-stats]');stats.replaceChildren();for(const [label,key,unit] of [['Minimum','min_rtt',' ms'],['Maximum','max_rtt',' ms'],['Jitter','jitter',' ms'],['Packet loss','loss',' %'],['Dostupnost','uptime',' %'],['Výpadky','incidents','']]){const card=el('article',null,stats);el('small',label,card);el('strong',fmt(device.stats[key],unit),card);}
 const incidents=$('[data-pd-incidents]');incidents.replaceChildren();
 if(!data.incidents.length)el('p','Žádný potvrzený výpadek v tomto období.',incidents);else{const table=el('table',null,incidents),head=el('tr',null,el('thead',null,table));for(const label of ['Začátek','Konec / stav','Délka'])el('th',label,head);const body=el('tbody',null,table);for(const i of data.incidents.slice(0,20)){const row=el('tr',null,body);el('td',date(i.start),row);el('td',i.end?date(i.end)+(i.end_reason==='monitoring_gap'?' · další stav neznámý':''):'Probíhá',row);el('td',fmt((i.end||Date.now()/1000)-i.start,' s'),row);}}
 redraw();$('[data-pd-error]').hidden=true;$('[data-pd-updated]').textContent=date(data.start)+' — '+date(data.end)+' · obnova každých 15 s';
 }catch(e){$('[data-pd-error]').hidden=false;$('[data-pd-error]').textContent=e.message;}finally{busy=false;}
}
root.querySelectorAll('[data-range]').forEach(button=>button.onclick=()=>{period=Number(button.dataset.range);end=null;root.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',b===button));refresh();});
$('[data-pd-back]').onclick=()=>{end=(end||Date.now()/1000)-period;refresh();};$('[data-pd-forward]').onclick=()=>{end=Math.min(Date.now()/1000,(end||Date.now()/1000)+period);refresh();};$('[data-pd-zoom]').onclick=()=>{period=Math.max(60,period/2);refresh();};$('[data-pd-live]').onclick=()=>{end=null;refresh();};
new ResizeObserver(redraw).observe(root);new MutationObserver(redraw).observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});setInterval(()=>{if(!document.hidden&&!end)refresh();},15000);refresh();
})();
