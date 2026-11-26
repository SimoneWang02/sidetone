"""A page that plays every character in every moment, from the sheets the hub really draws.

Run: ~/.local/share/kokoro/venv/bin/python -I tests/characters_page.py OUT_DIR
Writes OUT_DIR/index.html and OUT_DIR/sheets/*.png (each style, each of the first five session
colors). The page plays them as the overlay does: 12 frames a second, needs you and done play
their start once then repeat their end, speaking picks its row by a made-up voice's loudness.
The author, 2026-11-26: "can you give me a preview page for each character, each animation".
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hub"))
import characters  # noqa: E402
from state import COLORS  # noqa: E402

NAMES = {
    "familiars": ["Lantern, calm", "Ember, excitable", "Sprout, sleepy", "Shellback, shy", "Toadstool, grumpy"],
    "operators": ["Hoodie with cat ears", "Pendant", "Bandana", "Earbuds and a beard", "Aerial and a scarf"],
    "sketch": ["Blue session", "Orange session", "Violet session", "Teal session", "Pink session"],
}
ABOUT = {
    "familiars": "Five creatures with five tempers. Pixel art, shown with hard edges at twice its size.",
    "operators": "Five people on the line, each with their own headset and something of their own. Pixel art, twice its size.",
    "sketch": "One operator in pencil for every session; the scarf and headset take the session's color. Smooth lines, drawn at the size shown on the edge.",
}

PAGE = r"""<meta name="claude:viewport-fit-sides" content="cover">
<title>Sidetone Characters</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=Nunito+Sans:wght@400;600;700&display=swap">
<style>
/* Layout: one style at a time; a table of figures (rows) by moments (columns), each cell playing its sheet as the overlay does, on the overlay's own dark glass. */
:root{--bg:#10171c;--glass:#1c212b;--cell:#232835;--fg:#e8f0f3;--soft:#9db1bb;--line:#33404a;--accent:#58b4dc;--on:#08161d;--display:"Bricolage Grotesque",system-ui,sans-serif;--body:"Nunito Sans",system-ui,sans-serif;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:400 15px/1.5 var(--body)}
main{max-width:1060px;margin:0 auto;padding-block:26px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:16px}
h1{font:700 clamp(26px,4vw,34px)/1.1 var(--display);margin:0;text-wrap:balance}
header p{margin:6px 0 0;max-width:68ch;color:var(--soft)}
.bar{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center}
.group{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.group>span{font:700 12px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);margin-right:4px}
button{font:600 14px/1 var(--body);padding:9px 12px;border-radius:9px;border:1px solid var(--line);background:var(--glass);color:var(--fg);cursor:pointer}
button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--on)}
button:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
#about{margin:0;color:var(--soft);max-width:68ch}
.wrap{overflow-x:auto;border-radius:14px;background:var(--glass);border:1px solid var(--line)}
table{border-collapse:separate;border-spacing:6px;margin:4px}
th{font:700 12px/1.2 var(--body);letter-spacing:.05em;text-transform:uppercase;color:var(--soft);padding:6px 4px;text-align:center;white-space:nowrap}
th.who{text-align:left;text-transform:none;letter-spacing:0;font-size:13.5px;color:var(--fg);min-width:118px}
th.who i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:1px}
td{background:var(--cell);border-radius:10px;padding:6px;text-align:center;cursor:pointer}
td:hover{box-shadow:inset 0 0 0 1px var(--line)}
canvas{display:block;margin:0 auto}
.note{color:var(--soft);font-size:13.5px;margin:0}
</style>
<main>
<header><h1>Sidetone Characters</h1><p>Every figure in every moment, played from the very sheets the overlay reads, twelve frames a second. Needs You and Done play their start once, then repeat their end, as in the overlay; click a cell or Replay to see a start again.</p></header>
<div class="bar">
  <div class="group" id="styles" role="group" aria-label="Character"><span>Character</span></div>
  <div class="group" id="sizes" role="group" aria-label="Size"><span>Size</span></div>
  <div class="group"><button type="button" id="replay">Replay</button><button type="button" id="pause" aria-pressed="false">Pause</button></div>
</div>
<p id="about"></p>
<div class="wrap"><table id="grid"></table></div>
<p class="note">Sizes are the overlay's: In the List 35 px, Inside the bubble 66 px, On the Edge 88 px; Up Close is twice the edge. Speaking follows a made-up voice, so the mouth opens and closes as with real speech.</p>
</main>
<script>
const DATA = __DATA__;
const MOMENTS=[["idle","Idle"],["working","Working"],["speaking","Speaking"],["needs","Needs You"],["done","Done"],["failed","Failed"],["listen","Listening"]];
const SIZES=[["In the List",35],["Inside",66],["On the Edge",88],["Up Close",176]];
const L=DATA.layout, FPS=L.fps, ROWS=L.rows, CELL=L.cell;
let style="familiars", size=88, paused=matchMedia("(prefers-reduced-motion: reduce)").matches, started=performance.now();
const images={}, cells=[];
for(const s of Object.keys(DATA.styles))DATA.styles[s].forEach((f,i)=>{const im=new Image();im.src=f.file;images[s+i]=im});
const el=id=>document.getElementById(id);
function button(parent,label,on,pick){const b=document.createElement("button");b.type="button";b.textContent=label;b.setAttribute("aria-pressed",on);b.onclick=()=>{parent.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed","false"));b.setAttribute("aria-pressed","true");pick()};parent.append(b)}
Object.keys(DATA.styles).forEach(s=>button(el("styles"),DATA.names[s],s===style,()=>{style=s;build()}));
SIZES.forEach(([n,z])=>button(el("sizes"),n,z===size,()=>{size=z;build()}));
el("replay").onclick=()=>{started=performance.now();cells.forEach(c=>c.since=started)};
el("pause").onclick=e=>{paused=!paused;e.currentTarget.setAttribute("aria-pressed",paused);e.currentTarget.textContent=paused?"Play":"Pause"};
if(paused){el("pause").setAttribute("aria-pressed","true");el("pause").textContent="Play"}
const voice=t=>{const p=(t*25)%37;return p>30?0:Math.min(1,Math.abs(Math.sin(t*13.7))*(.6+.4*Math.sin(t*3.2)))};
let loud=0;
function build(){const g=el("grid");g.replaceChildren();cells.length=0;el("about").textContent=DATA.about[style];
  const head=g.insertRow();const c0=document.createElement("th");head.append(c0);
  MOMENTS.forEach(([,n])=>{const th=document.createElement("th");th.scope="col";th.textContent=n;head.append(th)});
  const dpr=Math.min(3,devicePixelRatio||1);
  DATA.styles[style].forEach((f,i)=>{const tr=g.insertRow();const th=document.createElement("th");th.scope="row";th.className="who";th.innerHTML=`<i style="background:${f.color}"></i>`;th.append(f.name);tr.append(th);
    MOMENTS.forEach(([m,n])=>{const td=tr.insertCell();const cv=document.createElement("canvas");cv.width=Math.round(size*dpr);cv.height=Math.round(size*dpr);cv.style.width=cv.style.height=size+"px";cv.setAttribute("role","img");cv.setAttribute("aria-label",f.name+", "+n);td.append(cv);
      const c={cv,g:cv.getContext("2d"),im:images[style+i],m,since:started,smooth:f.cell>CELL,cell:f.cell};td.onclick=()=>{c.since=performance.now()};cells.push(c)})});
  draw(performance.now(),true)}
function rowFor(c,now){let a=(now-c.since)/1000,row=c.m;
  if(c.m==="speaking")row="speaking"+(loud<.12?0:loud<.4?1:loud<.7?2:3);
  if((c.m==="needs"||c.m==="done")&&a*FPS>=ROWS[c.m][1]){row=c.m+"_hold";a-=ROWS[c.m][1]/FPS}
  const r=ROWS[row];return[r[0],Math.floor(a*FPS)%r[1]]}
let last=0;
function draw(now,force){if(!force&&(paused||now-last<1000/FPS-2))return;last=now;const v=voice(now/1000);loud+=(v-loud)*(v>loud?.5:.28);
  for(const c of cells){if(!c.im.complete||!c.im.naturalWidth)continue;const[r,col]=rowFor(c,now);const g=c.g;g.setTransform(1,0,0,1,0,0);g.clearRect(0,0,c.cv.width,c.cv.height);g.imageSmoothingEnabled=c.smooth;g.imageSmoothingQuality="high";g.drawImage(c.im,col*c.cell,r*c.cell,c.cell,c.cell,0,0,c.cv.width,c.cv.height)}}
function tick(now){requestAnimationFrame(tick);draw(now,false)}
Object.values(images).forEach(im=>im.addEventListener("load",()=>draw(performance.now(),true)));
build();requestAnimationFrame(tick);
</script>
"""


def main(out: str) -> None:
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    styles = {}
    for style in characters.STYLES:
        styles[style] = []
        for i, color in enumerate(COLORS[:5]):
            name = f"sheets/{style}-{i}.png"
            with open(os.path.join(out, name), "wb") as f:
                f.write(characters.sheet(style, characters.kind_of(color), color))
            styles[style].append({"file": name, "color": color, "name": NAMES[style][i], "cell": characters.cell(style)})
    data = {"layout": characters.LAYOUT, "styles": styles, "about": ABOUT,
            "names": {"familiars": "Familiars", "operators": "Operators", "sketch": "Sketch"}}
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(data)))
    print(os.path.join(out, "index.html"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "characters-page")
