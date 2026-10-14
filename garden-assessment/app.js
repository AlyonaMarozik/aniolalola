'use strict';
(function(){
const $=id=>document.getElementById(id),svg=$('assessment-svg'),layer=$('assessment-plants'),ns='http://www.w3.org/2000/svg';
const seasons={spring:[3,4,5],summer:[6,7,8],autumn:[9,10,11],winter:[12,1,2]},months=['','Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
let season='all',month=null,age=10,effect='all',hideBg=false,selected=null,plants=[],extras=[],serial=0;
function coordinate(cell){const m=/^([ABCD])(\d+)$/.exec(cell);return m?{x:(19-Number(m[2]))*.5+.25,y:{D:.2,C:.7,B:1.2,A:1.7}[m[1]]}:null}
function range(s){const a=[];String(s||'').split(',').filter(Boolean).forEach(t=>{const v=t.split('-').map(Number);for(let i=v[0];i<=(v[1]||v[0]);i++)a.push(i)});return a}
function traits(n){const s=n.toLowerCase();let adult=.8,flower='6-9',leaf='4-10',color='#a2b58a';
if(/limelight|candlelight|skyfall|wim|hydrangea|blue bird|blue ball|гортензия|bee green/.test(s)){adult=1.6;flower='7-10';color='#8cadd0'}
if(/rose|rosa|boscobel|dannahue|summer song|eustacia|queen of sweden|roald dahl|golden celebration/.test(s)){adult=1.1;flower='6-10';color='#d992a6'}
if(/sakura|сакура|shidare/.test(s)){adult=3.2;flower='4-5';color='#e5a4be'}
if(/клён/.test(s)){adult=2.5;flower='';color='#b45b66'}
if(/asplenium|cyrtomium|pieris|impeditum/.test(s)){adult=.6;flower='';leaf='1-12';color='#568569'}
if(/athyrium|adiantum/.test(s)){adult=.65;flower='';color='#7eac92'}
if(/helleborus/.test(s)){adult=.55;flower='2-4';leaf='1-12';color='#bc9db5'}
if(/cyclamen/.test(s)){adult=.25;flower='1-3';leaf='1-5,10-12';color='#e5e5d9'}
return{adult,now:Math.min(.3,adult),flower:range(flower),leaf:range(leaf),color}}
function make(n,cell,id){return{...coordinate(cell),...traits(n),name:n,cell,id,background:false,fixed:true}}
function rebuild(){
const prior=new Map(plants.map(p=>[p.id,p])),next=[];
for(const [cell,name] of Object.entries(names)){if(coordinate(cell))next.push(make(name,cell,'fact:'+cell))}
const grouped=new Map();for(const [cell,name] of Object.entries(state.plan||{})){if(!name||!state.locked.includes(cell)||!coordinate(cell)||!inventory.some(p=>p.name===name))continue;if(!grouped.has(name))grouped.set(name,[]);grouped.get(name).push(cell)}
for(const [name,cells] of grouped){const unique=name==='Boscobel'&&cells.includes('B16')&&cells.includes('C16')?['B16']:cells;unique.forEach((cell,i)=>{const p=make(name,cell,'plan:'+name+':'+i);if(name==='Boscobel'&&unique.length===1&&cells.includes('C16')){p.x=(coordinate('B16').x+coordinate('C16').x)/2;p.y=(coordinate('B16').y+coordinate('C16').y)/2}next.push(p)})}
const occupied=new Set(next.map(p=>p.cell));for(const [set,name,color,d,leaf] of [[pine,'Сосна','#43794e',.35,'1-12'],[bush,'Барбарис','#b45767',.25,'4-11']])for(const cell of set){if(!coordinate(cell)||occupied.has(cell))continue;next.push({...make(name,cell,'background:'+name+':'+cell),background:true,fixed:false,now:d,adult:d,color,flower:[],leaf:range(leaf)})}
plants=next.map(p=>{const old=prior.get(p.id);return old?{...p,x:old.x,y:old.y,now:old.now,adult:old.adult}:p});render()
}
// Only uncommitted, unplanted hill inventory can be added as an assessment experiment.
// A confirmed Fact specimen is not a movable second copy. Locked/draft Plan spots
// already reserve their inventory specimens, even when only locked spots are rendered.
function assessmentAvailable(item){
 if(item.assessment_scope==='outside_hill')return 0;
 const total=Number(item.count)||0;
 const confirmed=Math.min(total,Math.max(Number(item.planted_count)||0,Number(state.planted?.[item.name])||0));
 const reserved=Object.entries(state.plan||{}).filter(([cell,name])=>name===item.name&&coordinate(cell)).length;
 const planned=(item.name==='Boscobel'&&state.plan?.B16==='Boscobel'&&state.plan?.C16==='Boscobel')?reserved-1:reserved;
 const visual=extras.filter(p=>p.name===item.name).length;
 return Math.max(0,total-confirmed-planned-visual);
}
function all(){return [...plants,...extras]}function diameter(p){return p.now+(p.adult-p.now)*age/10}
function shown(p){return !(hideBg&&p.background&&!p.fixed)}
function active(p){if(season==='all')return true;const mm=month===null?seasons[season]:[month];return mm.some(m=>(effect!=='leaf'&&p.flower.includes(m))||(effect!=='flower'&&p.leaf.includes(m)))}
function controls(id,items,value,fn){const el=$(id);el.replaceChildren();for(const [label,v] of items){const b=document.createElement('button');b.textContent=label;if(v===value)b.className='on';b.onclick=()=>fn(v);el.append(b)}}
function draw(tag,attrs){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);layer.append(n);return n}
function labelLines(name){
const words=String(name||'').trim().split(/\s+/).filter(Boolean);
const lines=[''];
for(const word of words){
let row=lines.length-1;
let limit=Math.min(13,25-(row?Array.from(lines[0]).length:0));
const proposal=lines[row]?lines[row]+' '+word:word;
if(Array.from(proposal).length<=limit){lines[row]=proposal;continue}
if(row===0&&lines[0]){
lines.push('');row=1;limit=Math.min(13,25-Array.from(lines[0]).length);
if(Array.from(word).length<=limit){lines[1]=word;continue}
}
if(row===0){
lines[0]=Array.from(word).slice(0,12).join('')+'…';
continue;
}
const current=Array.from(lines[1]);
if(!current.length)lines[1]=Array.from(word).slice(0,Math.max(0,limit-1)).join('')+'…';
else if(current.length<limit)lines[1]+='…';
else lines[1]=current.slice(0,limit-1).join('')+'…';
break;
}
return lines.filter(Boolean);
}
function render(){
controls('assessment-season',[['Все','all'],['Весна','spring'],['Лето','summer'],['Осень','autumn'],['Зима','winter']],season,v=>{season=v;month=null;render()});
$('assessment-month').hidden=season==='all';if(season!=='all')controls('assessment-month',[['Весь сезон',null],...seasons[season].map(m=>[months[m],m])],month,v=>{month=v;render()});
controls('assessment-age',[['Сейчас',0],['3 года',3],['5 лет',5],['10 лет',10]],age,v=>{age=v;render()});
controls('assessment-effect',[['Вся декоративность','all'],['Цветение','flower'],['Листва / структура','leaf']],effect,v=>{effect=v;render()});
$('assessment-bg').textContent=hideBg?'Показать фон':'Убрать фон';$('assessment-bg').classList.toggle('on',hideBg);layer.replaceChildren();
let count=0;for(const p of all()){if(!shown(p))continue;count++;const x=p.x*100,y=58+p.y*100,r=diameter(p)*50,on=active(p);draw('circle',{cx:x,cy:y,r,fill:on?p.color:'none','fill-opacity':on?.43:0,stroke:p.id===selected?'#aa772c':on?p.color:'#9ca79b','stroke-width':p.id===selected?4:1.5,'stroke-dasharray':on?'none':'5 5'});if(on||p.id===selected){const lines=labelLines(p.name);const t=draw('text',{x,y:y+(lines.length===2?-3:3),'text-anchor':'middle','font-size':10,'font-weight':600,fill:'#293b30','pointer-events':'none'});for(const [i,line] of lines.entries()){const span=document.createElementNS(ns,'tspan');span.setAttribute('x',x);if(i)span.setAttribute('dy','11');span.textContent=line;t.append(span)}}}
const p=all().find(p=>p.id===selected);$('assessment-selected').textContent=p?p.name+' · '+diameter(p).toFixed(2)+' м · '+(p.background?'фон':p.fixed?'из Плана':'визуал'):'Выбери кружочек';$('assessment-count').textContent=count+' кружочков · изменения не записываются в План';
const sel=$('assessment-add'),prev=sel.value;sel.replaceChildren(new Option('— Свободное растение для горки —',''));for(const item of inventory){const left=assessmentAvailable(item);if(left>0)sel.append(new Option(item.name+' · доступно '+left,item.name))}if([...sel.options].some(o=>o.value===prev))sel.value=prev;
}
$('assessment-bg').onclick=()=>{hideBg=!hideBg;render()};
$('assessment-reset').onclick=()=>{if(confirm('Сбросить только визуальные эксперименты?')){plants=[];extras=[];selected=null;rebuild()}};
$('assessment-add-btn').onclick=()=>{const name=$('assessment-add').value,item=inventory.find(p=>p.name===name);if(!item||assessmentAvailable(item)<1){render();return}const p={...traits(name),name,cell:'',id:'extra:'+(++serial),x:5,y:1,fixed:false,background:false};extras.push(p);selected=p.id;render()};
function resize(d){const p=all().find(p=>p.id===selected);if(!p)return;const key=age===0?'now':'adult';p[key]=Math.max(.1,p[key]+d);render()}
$('assessment-minus').onclick=()=>resize(-.1);$('assessment-plus').onclick=()=>resize(.1);
$('assessment-remove').onclick=()=>{if(!String(selected).startsWith('extra:'))return;extras=extras.filter(p=>p.id!==selected);selected=null;render()};
function point(e){const r=svg.getBoundingClientRect();return{x:(e.clientX-r.left)*1000/r.width,y:(e.clientY-r.top)*365/r.height}}
let pointers=new Map(),drag=null,pinch=null;
svg.addEventListener('pointerdown',e=>{e.preventDefault();svg.setPointerCapture(e.pointerId);const q=point(e);pointers.set(e.pointerId,q);if(pointers.size===1){const p=all().filter(shown).reverse().find(p=>Math.hypot(q.x-p.x*100,q.y-58-p.y*100)<=Math.max(12,diameter(p)*50));selected=p?.id||null;drag=p?{id:p.id,dx:q.x-p.x*100,dy:q.y-58-p.y*100}:null;render()}else if(pointers.size===2&&selected){const a=[...pointers.values()],p=all().find(p=>p.id===selected);pinch={distance:Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y),value:age===0?p.now:p.adult};drag=null}});
svg.addEventListener('pointermove',e=>{if(!pointers.has(e.pointerId))return;e.preventDefault();const q=point(e);pointers.set(e.pointerId,q);if(pointers.size===2&&pinch){const a=[...pointers.values()],d=Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y),p=all().find(p=>p.id===selected);if(p){p[age===0?'now':'adult']=Math.max(.1,Math.min(10,pinch.value+(d-pinch.distance)/100));render()}}else if(pointers.size===1&&drag){const p=all().find(p=>p.id===drag.id);if(p){p.x=Math.max(-2,Math.min(12,(q.x-drag.dx)/100));p.y=Math.max(-.3,Math.min(3,(q.y-drag.dy-58)/100));render()}}});
function end(e){pointers.delete(e.pointerId);if(pointers.size<2)pinch=null;if(!pointers.size)drag=null}svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);
window.addEventListener('garden-plan-changed',rebuild);window.addEventListener('garden-assessment-open',rebuild);rebuild();
})();