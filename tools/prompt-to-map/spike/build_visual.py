#!/usr/bin/env python3
"""SPIKE: assemble a self-contained tactical map-inspector HTML from parsed maps.

Injects the parsed JSON (terrain grid + objects + player starts) into a single
dark 'command console' page that renders real C&C: Generals maps from the bytes
we decoded. No external assets (Artifact CSP-safe)."""
import json
import sys

maps = [json.load(open(p, encoding="utf-8")) for p in sys.argv[1:-1]]
out_path = sys.argv[-1]
DATA = json.dumps(maps, separators=(",", ":"))

HTML = r"""<style>
:root{
  --bg:#090d12; --panel:#0f151c; --panel2:#141d26; --line:#233240;
  --ink:#cdd9e2; --dim:#6d818f; --amber:#ffb43a; --amber2:#b97f27;
  --green:#5fd06a; --red:#e5484d; --blue:#4c8dff;
  --mono:ui-monospace,"Cascadia Code","JetBrains Mono",Consolas,monospace;
  --sans:"Segoe UI",Inter,system-ui,-apple-system,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
  -webkit-font-smoothing:antialiased;line-height:1.5}
.wrap{max-width:1200px;margin:0 auto;padding:28px 22px 60px}

/* header */
.masthead{display:flex;align-items:flex-end;justify-content:space-between;
  gap:20px;border-bottom:1px solid var(--line);padding-bottom:16px;flex-wrap:wrap}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.28em;
  text-transform:uppercase;color:var(--amber);margin:0 0 8px}
h1{font-size:clamp(30px,5vw,50px);margin:0;font-weight:800;letter-spacing:.02em;
  text-transform:uppercase;line-height:.95;text-wrap:balance}
h1 .thin{color:var(--dim);font-weight:300}
.sub{color:var(--dim);font-size:13.5px;max-width:46ch;margin:10px 0 0}
.stamp{font-family:var(--mono);font-size:10.5px;color:var(--dim);text-align:right;
  line-height:1.7;white-space:nowrap}
.stamp b{color:var(--green)}

/* layout */
.deck{display:grid;grid-template-columns:1fr 296px;gap:20px;margin-top:24px}
@media(max-width:820px){.deck{grid-template-columns:1fr}}

/* console / canvas */
.console{position:relative;background:
  radial-gradient(120% 120% at 50% 0%,#12202a 0%,#0a1119 60%,#070c11 100%);
  border:1px solid var(--line);border-radius:6px;overflow:hidden;
  box-shadow:inset 0 0 60px rgba(0,0,0,.6),0 12px 40px rgba(0,0,0,.4)}
.console::after{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,.14) 0 1px,transparent 1px 3px);
  mix-blend-mode:multiply;opacity:.5}
.console .corner{position:absolute;width:14px;height:14px;border:2px solid var(--amber);
  opacity:.7;pointer-events:none}
.c-tl{top:8px;left:8px;border-right:0;border-bottom:0}
.c-tr{top:8px;right:8px;border-left:0;border-bottom:0}
.c-bl{bottom:8px;left:8px;border-right:0;border-top:0}
.c-br{bottom:8px;right:8px;border-left:0;border-top:0}
canvas{display:block;width:100%;height:auto;image-rendering:auto}
.readout-top{position:absolute;top:12px;left:16px;font-family:var(--mono);
  font-size:11px;letter-spacing:.12em;color:var(--amber);text-transform:uppercase;
  text-shadow:0 0 8px rgba(255,180,58,.4);pointer-events:none}
.readout-top .nm{color:var(--ink)}
.tip{position:absolute;pointer-events:none;background:rgba(8,12,17,.94);
  border:1px solid var(--amber2);border-radius:4px;padding:6px 9px;font-family:var(--mono);
  font-size:11px;color:var(--ink);transform:translate(-50%,-135%);white-space:nowrap;
  opacity:0;transition:opacity .1s;z-index:5}
.tip b{color:var(--amber)}

/* sidebar panels */
.side{display:flex;flex-direction:column;gap:14px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:14px 15px}
.panel h2{font-family:var(--mono);font-size:10.5px;letter-spacing:.24em;text-transform:uppercase;
  color:var(--dim);margin:0 0 12px;display:flex;align-items:center;gap:8px}
.panel h2::before{content:"";width:6px;height:6px;background:var(--amber);
  box-shadow:0 0 6px var(--amber);border-radius:1px}

.mapbtns{display:grid;gap:8px}
.mapbtn{appearance:none;text-align:left;background:var(--panel2);color:var(--ink);
  border:1px solid var(--line);border-radius:5px;padding:10px 12px;cursor:pointer;
  font-family:var(--sans);transition:border-color .15s,background .15s}
.mapbtn:hover{border-color:var(--amber2)}
.mapbtn[aria-pressed=true]{border-color:var(--amber);background:#1a2530;
  box-shadow:inset 0 0 0 1px rgba(255,180,58,.25)}
.mapbtn .t{font-weight:700;font-size:14px;letter-spacing:.01em}
.mapbtn .m{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:3px}
.mapbtn:focus-visible{outline:2px solid var(--amber);outline-offset:2px}

.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px 12px}
.stat .k{font-family:var(--mono);font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim)}
.stat .v{font-family:var(--mono);font-size:20px;color:var(--ink);font-variant-numeric:tabular-nums;margin-top:2px}
.stat .v small{font-size:12px;color:var(--dim)}

.layers{display:flex;flex-direction:column;gap:2px}
.layer{display:flex;align-items:center;gap:10px;padding:6px 4px;cursor:pointer;border-radius:4px;
  font-size:13px;user-select:none}
.layer:hover{background:var(--panel2)}
.layer input{appearance:none;width:0;height:0;margin:0}
.swatch{width:12px;height:12px;border-radius:3px;flex:0 0 auto;box-shadow:0 0 0 1px rgba(255,255,255,.08)}
.layer .cnt{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--dim);font-variant-numeric:tabular-nums}
.layer.off{opacity:.4}
.layer .box{width:14px;height:14px;border:1px solid var(--dim);border-radius:3px;
  display:grid;place-items:center;flex:0 0 auto}
.layer:not(.off) .box{border-color:var(--amber);background:rgba(255,180,58,.12)}
.layer:not(.off) .box::after{content:"";width:7px;height:7px;background:var(--amber);border-radius:1px}

/* pipeline */
.pipe{display:flex;flex-direction:column;gap:0}
.pstep{display:flex;gap:11px;align-items:flex-start;position:relative;padding:0 0 14px 0}
.pstep:last-child{padding-bottom:0}
.pdot{width:11px;height:11px;border-radius:50%;border:2px solid var(--green);flex:0 0 auto;margin-top:3px;
  background:var(--bg);position:relative;z-index:1}
.pstep:not(:last-child)::before{content:"";position:absolute;left:5px;top:12px;bottom:0;
  width:1px;background:var(--line)}
.pstep .pt{font-size:12.5px}
.pstep .pt b{font-family:var(--mono);color:var(--green);font-weight:600}
.pstep .pm{font-family:var(--mono);font-size:10.5px;color:var(--dim);margin-top:1px}

.foot{margin-top:26px;border-top:1px solid var(--line);padding-top:14px;
  font-size:12.5px;color:var(--dim);max-width:70ch}
.foot b{color:var(--ink)}
.blink{animation:bk 1.4s steps(2) infinite}
@keyframes bk{50%{opacity:.25}}
@media(prefers-reduced-motion:reduce){.blink{animation:none}}
</style>

<div class="wrap">
  <header class="masthead">
    <div>
      <p class="eyebrow">Tactical Data Reconstruction</p>
      <h1>Map&nbsp;Inspector <span class="thin">/ Zero&nbsp;Hour</span></h1>
      <p class="sub">Every pixel below is decoded straight from a retail
        <b style="color:var(--ink)">.map</b> file &mdash; decompressed, its chunk tree
        parsed, terrain and units read by coordinate. No screenshots. This is the read
        pipeline that the prompt&#8209;to&#8209;map generator will run in reverse.</p>
    </div>
    <div class="stamp">
      SYSTEM &middot; <b>ONLINE</b><br>
      SOURCE &middot; MapsZH.big<br>
      DECODE &middot; <b>OK</b> <span class="blink">&#9608;</span>
    </div>
  </header>

  <div class="deck">
    <div class="console">
      <div class="corner c-tl"></div><div class="corner c-tr"></div>
      <div class="corner c-bl"></div><div class="corner c-br"></div>
      <div class="readout-top">MAP&nbsp;&rsaquo;&nbsp;<span class="nm" id="ro-name">&mdash;</span></div>
      <canvas id="cv" width="900" height="900" aria-label="Rendered tactical map"></canvas>
      <div class="tip" id="tip"></div>
    </div>

    <aside class="side">
      <div class="panel">
        <h2>Map Select</h2>
        <div class="mapbtns" id="mapbtns"></div>
      </div>

      <div class="panel">
        <h2>Readout</h2>
        <div class="grid2">
          <div class="stat"><div class="k">Grid</div><div class="v" id="s-grid">&mdash;</div></div>
          <div class="stat"><div class="k">Border</div><div class="v" id="s-border">&mdash;</div></div>
          <div class="stat"><div class="k">Objects</div><div class="v" id="s-obj">&mdash;</div></div>
          <div class="stat"><div class="k">Starts</div><div class="v" id="s-start">&mdash;</div></div>
        </div>
      </div>

      <div class="panel">
        <h2>Layers</h2>
        <div class="layers" id="layers"></div>
      </div>

      <div class="panel">
        <h2>Decode Pipeline</h2>
        <div class="pipe" id="pipe"></div>
      </div>
    </aside>
  </div>

  <p class="foot">What you're looking at proves <b>Phase&nbsp;0</b>: a real Zero&nbsp;Hour
    map read end&#8209;to&#8209;end from raw bytes &mdash; EA RefPack decompression, the
    <b>CkMp</b> chunk container, the height grid, and every placed object with its faction
    start points. Reading the format correctly is the hard half of writing it. Next: emit
    a <b>.map</b> of our own and load it in&#8209;game.</p>
</div>

<script>
const MAPS = __DATA__;
const CELL = 10;
const KINDS = {
  start:   {c:"#ffffff", label:"Player starts"},
  resource:{c:"#ffcf4d", label:"Resources"},
  unit:    {c:"#9fb6c6", label:"Structures / units"},
  scenery: {c:"#4e8a58", label:"Scenery"},
  civilian:{c:"#a892e0", label:"Civilian"},
  tech:    {c:"#d98a4d", label:"Tech / neutral"},
  waypoint:{c:"#566876", label:"Waypoints"},
};
const FACTION = ["#e5484d","#4c8dff","#5fd06a","#f4c14b","#c96bd8","#ff8f4d","#43c7c7","#d0d5da"];
const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
const tip = document.getElementById("tip");
let cur = 0, shown = {}, hyfliphint = false;

// terrain elevation ramp (deep basin -> alpine/desert highland)
const RAMP = [[0,[18,34,44]],[0.12,[20,52,58]],[0.34,[29,58,46]],
  [0.56,[63,90,58]],[0.74,[122,125,69]],[0.88,[184,154,85]],[1,[232,207,143]]];
function ramp(t){
  for(let i=1;i<RAMP.length;i++){ if(t<=RAMP[i][0]){
    const a=RAMP[i-1],b=RAMP[i],f=(t-a[0])/(b[0]-a[0]||1);
    return [0,1,2].map(k=>Math.round(a[1][k]+(b[1][k]-a[1][k])*f)); } }
  return RAMP[RAMP.length-1][1];
}

function buildControls(){
  const mb=document.getElementById("mapbtns"); mb.innerHTML="";
  MAPS.forEach((m,i)=>{
    const b=document.createElement("button");
    b.className="mapbtn"; b.setAttribute("aria-pressed", i===cur);
    const starts=m.objects.filter(o=>o.k==="start").length;
    b.innerHTML=`<div class="t">${m.name}</div><div class="m">${m.width}×${m.height}`
      +` · ${starts} players · ${m.objects.length.toLocaleString()} obj</div>`;
    b.onclick=()=>{cur=i;selectMap();};
    mb.appendChild(b);
  });
}

function selectMap(){
  const m=MAPS[cur];
  document.querySelectorAll(".mapbtn").forEach((b,i)=>b.setAttribute("aria-pressed",i===cur));
  document.getElementById("ro-name").textContent=m.name;
  document.getElementById("s-grid").innerHTML=`${m.width}<small>×${m.height}</small>`;
  document.getElementById("s-border").textContent=m.border;
  document.getElementById("s-obj").textContent=m.objects.length.toLocaleString();
  document.getElementById("s-start").textContent=m.objects.filter(o=>o.k==="start").length;
  // layers
  const counts={}; m.objects.forEach(o=>counts[o.k]=(counts[o.k]||0)+1);
  const host=document.getElementById("layers"); host.innerHTML="";
  Object.keys(KINDS).forEach(k=>{
    if(!counts[k]) return;
    if(shown[k]===undefined) shown[k]=(k!=="waypoint");
    const row=document.createElement("label");
    row.className="layer"+(shown[k]?"":" off");
    row.innerHTML=`<span class="box"></span>`
      +`<span class="swatch" style="background:${KINDS[k].c}"></span>`
      +`<span>${KINDS[k].label}</span><span class="cnt">${counts[k]}</span>`;
    row.onclick=()=>{shown[k]=!shown[k];row.classList.toggle("off",!shown[k]);draw();};
    host.appendChild(row);
  });
  // pipeline
  const cbytes=m.cbytes||m.width; // fallback
  const pipe=document.getElementById("pipe");
  const steps=[
    ["Extract","from MapsZH.big archive"],
    ["RefPack → raw","EAR\\0 envelope decompressed"],
    ["CkMp TOC","name table + chunk tree"],
    ["Read grid + objects",`${m.width*m.height} cells · ${m.objects.length} objects`],
  ];
  pipe.innerHTML=steps.map(s=>`<div class="pstep"><div class="pdot"></div>`
    +`<div><div class="pt"><b>${s[0]}</b></div><div class="pm">${s[1]}</div></div></div>`).join("");
  fitCanvas(); draw(true);
}

function fitCanvas(){
  const m=MAPS[cur], W=cv.clientWidth||880;
  const asp=m.height/m.width;
  cv.width=Math.round(W*devicePixelRatio);
  cv.height=Math.round(W*asp*devicePixelRatio);
}

let terrainCache=null, terrainKey="";
function terrain(m){
  const key=m.name+"|"+cv.width;
  if(terrainKey===key) return terrainCache;
  const off=document.createElement("canvas"); off.width=m.hw; off.height=m.hh;
  const octx=off.getContext("2d"), img=octx.createImageData(m.hw,m.hh);
  let lo=255,hi=0; for(const v of m.heights){if(v<lo)lo=v;if(v>hi)hi=v;}
  const rng=(hi-lo)||1;
  for(let i=0;i<m.heights.length;i++){
    const t=(m.heights[i]-lo)/rng, c=ramp(t);
    // subtle hillshade from west neighbour
    const x=i%m.hw, left=x>0?m.heights[i-1]:m.heights[i];
    const sh=Math.max(-16,Math.min(20,(m.heights[i]-left)*3));
    img.data[i*4]=Math.max(0,Math.min(255,c[0]+sh));
    img.data[i*4+1]=Math.max(0,Math.min(255,c[1]+sh));
    img.data[i*4+2]=Math.max(0,Math.min(255,c[2]+sh));
    img.data[i*4+3]=255;
  }
  octx.putImageData(img,0,0);
  terrainCache=off; terrainKey=key; return off;
}

function toPx(m,x,y){
  return [ (x/CELL)/m.width*cv.width, (y/CELL)/m.height*cv.height ];
}

let intro=0, introRAF=null;
function draw(animate){
  const m=MAPS[cur];
  ctx.clearRect(0,0,cv.width,cv.height);
  // terrain
  ctx.imageSmoothingEnabled=true;
  ctx.drawImage(terrain(m),0,0,cv.width,cv.height);
  // faint tactical grid
  ctx.strokeStyle="rgba(120,150,165,.08)"; ctx.lineWidth=1;
  const gs=cv.width/16;
  for(let i=1;i<16;i++){ctx.beginPath();ctx.moveTo(i*gs,0);ctx.lineTo(i*gs,cv.height);ctx.stroke();}
  for(let i=1;i<Math.round(16*m.height/m.width);i++){ctx.beginPath();ctx.moveTo(0,i*gs);ctx.lineTo(cv.width,i*gs);ctx.stroke();}
  // playable border
  const [bx0,by0]=toPx(m,m.border*CELL,m.border*CELL);
  const [bx1,by1]=toPx(m,(m.width-m.border)*CELL,(m.height-m.border)*CELL);
  ctx.strokeStyle="rgba(255,180,58,.45)"; ctx.setLineDash([6,5]); ctx.lineWidth=1.5;
  ctx.strokeRect(bx0,by0,bx1-bx0,by1-by0); ctx.setLineDash([]);
  // objects
  const dpr=devicePixelRatio, r=2.1*dpr;
  const starts=[];
  for(const o of m.objects){
    if(o.k==="start"){starts.push(o);continue;}
    if(!shown[o.k]) continue;
    const [px,py]=toPx(m,o.x,o.y);
    ctx.fillStyle=KINDS[o.k].c; ctx.globalAlpha=o.k==="scenery"?.72:.92;
    ctx.beginPath(); ctx.arc(px,py,o.k==="resource"?r*1.5:r,0,7); ctx.fill();
  }
  ctx.globalAlpha=1;
  // player starts on top
  if(shown.start!==false){
    starts.forEach((o)=>{
      const idx=(parseInt((o.w||"").replace(/\D/g,""))||1)-1;
      const col=FACTION[idx%FACTION.length];
      const [px,py]=toPx(m,o.x,o.y);
      ctx.beginPath();ctx.arc(px,py,11*dpr,0,7);
      ctx.fillStyle=col+"22";ctx.fill();
      ctx.lineWidth=2*dpr;ctx.strokeStyle=col;ctx.beginPath();ctx.arc(px,py,8*dpr,0,7);ctx.stroke();
      ctx.fillStyle=col;ctx.beginPath();ctx.arc(px,py,3*dpr,0,7);ctx.fill();
      ctx.fillStyle="#fff";ctx.font=`700 ${11*dpr}px ui-monospace,monospace`;
      ctx.textAlign="center";ctx.textBaseline="middle";
      ctx.fillText(String(idx+1),px,py-15*dpr);
    });
  }
  // intro scan sweep
  if(animate && !matchMedia("(prefers-reduced-motion:reduce)").matches){
    cancelAnimationFrame(introRAF); intro=0;
    const step=()=>{ intro+=0.035; if(intro>=1)return;
      draw(false);
      const y=intro*cv.height;
      const g=ctx.createLinearGradient(0,y-40*dpr,0,y);
      g.addColorStop(0,"rgba(255,180,58,0)");g.addColorStop(1,"rgba(255,180,58,.5)");
      ctx.fillStyle=g;ctx.fillRect(0,y-40*dpr,cv.width,40*dpr);
      ctx.fillStyle="rgba(255,210,120,.9)";ctx.fillRect(0,y,cv.width,1.5*dpr);
      ctx.fillStyle="rgba(6,10,14,.55)";ctx.fillRect(0,y,cv.width,cv.height-y);
      introRAF=requestAnimationFrame(step);
    }; introRAF=requestAnimationFrame(step);
  }
}

// hover tooltip
cv.addEventListener("mousemove",e=>{
  const m=MAPS[cur], rect=cv.getBoundingClientRect();
  const mx=(e.clientX-rect.left)/rect.width*cv.width;
  const my=(e.clientY-rect.top)/rect.height*cv.height;
  let best=null,bd=14*devicePixelRatio;
  for(const o of m.objects){
    if(o.k!=="start"&&!shown[o.k])continue;
    const [px,py]=toPx(m,o.x,o.y);
    const d=Math.hypot(px-mx,py-my);
    if(d<bd){bd=d;best=o;}
  }
  if(best){
    tip.style.left=((toPx(m,best.x,best.y)[0])/cv.width*rect.width)+"px";
    tip.style.top=((toPx(m,best.x,best.y)[1])/cv.height*rect.height)+"px";
    const nm=best.w?`<b>${best.w}</b>`:best.n;
    tip.innerHTML=`${nm}<br>${best.n!==best.w?best.n+" · ":""}(${best.x|0}, ${best.y|0})`;
    tip.style.opacity=1;
  } else tip.style.opacity=0;
});
cv.addEventListener("mouseleave",()=>tip.style.opacity=0);

let rt; addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(()=>{fitCanvas();terrainKey="";draw(false);},120);});

buildControls(); selectMap();
</script>
"""

open(out_path, "w", encoding="utf-8").write(HTML.replace("__DATA__", DATA))
print("wrote", out_path, "bytes:", len(HTML) + len(DATA))
