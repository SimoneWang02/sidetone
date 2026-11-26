"""A page to try a session's subagents as small companions, from the sheets the hub really draws.

Run: ~/.local/share/kokoro/venv/bin/python -I tests/companions_page.py OUT_DIR
Writes OUT_DIR/index.html and OUT_DIR/sheets/*.png. The page stands in for the hub and the overlay
(`overlay.character_agents`): the same sizes (88 and 44 px), gaps, twelve frames a second, the
three-second cheer, the quarter-second fade, three and then a count, the task on hover.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "hub"), os.path.join(ROOT, "tests")]
import base  # noqa: E402
import characters  # noqa: E402
from characters_page import NAMES, colors  # noqa: E402

LABELS = {"familiars": "Familiars", "operators": "Operators", "sketch": "Sketch"}
SKETCHES = 2  # a pencil sheet is 250 kB and they differ only in the scarf's color

PAGE = r"""<meta name="claude:viewport-fit-sides" content="cover">
<title>Sidetone Companions</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700&family=Nunito+Sans:wght@400;600;700&display=swap">
<style>
/* Layout: the overlay's own corner at real size on a backdrop that can be switched, under the buttons that stand in for a session's subagents. One dark look, as the overlay has. */
:root{--bg:#10171c;--glass:#1c212b;--fg:#e8f0f3;--soft:#9db1bb;--line:#33404a;--accent:#58b4dc;--on:#08161d;--panel:#262a33;--tile:#30343e;--edge:rgba(255,255,255,.3);--chip:rgba(38,42,51,.9);--behind-dark:#15171b;--behind-light:#e9edf0;--display:"Bricolage Grotesque",system-ui,sans-serif;--body:"Nunito Sans",system-ui,sans-serif;--overlay:"Segoe UI",system-ui,sans-serif;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font:400 15px/1.5 var(--body)}
main{max-width:860px;margin:0 auto;padding-block:26px 48px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:16px}
h1{font:700 clamp(26px,4vw,34px)/1.1 var(--display);margin:0;text-wrap:balance}
header p,.note{margin:6px 0 0;max-width:68ch;color:var(--soft)}
.note{font-size:13.5px;margin:0}
.bar{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:center}
.group{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.group>span{font:700 12px/1 var(--body);letter-spacing:.06em;text-transform:uppercase;color:var(--soft);margin-right:4px}
button{font:600 14px/1 var(--body);padding:9px 12px;border-radius:9px;border:1px solid var(--line);background:var(--glass);color:var(--fg);cursor:pointer}
button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--on)}
button:focus-visible,canvas:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
#said{min-height:1.5em;color:var(--fg)}
.stage{--behind:var(--behind-dark);--z:1;background:var(--behind);border:1px solid var(--line);border-radius:14px;overflow:auto;padding:28px 16px 24px}
.stage.light{--behind:var(--behind-light)}
.zoom{width:min(380px,100%);margin:0 auto;height:calc(var(--z)*205px)}
.overlay{position:relative;width:100%;transform:scale(var(--z));transform-origin:top center;font-family:var(--overlay);color:var(--fg)}
.perch{display:flex;align-items:flex-end;width:max-content;height:88px;margin:0 6px -5px;position:relative;z-index:1}
.perch.mirrored{flex-direction:row-reverse;margin-left:auto}
.perch canvas{display:block;flex:none}
.perch.has .big{margin-right:-9px}
.perch.has.mirrored .big{margin-right:0;margin-left:-5px}
.small{margin-bottom:1px}
.chip{font:600 11px/15px var(--overlay);padding:1px 6px 2px;border-radius:9px;background:var(--chip);border:1px solid var(--edge);margin:0 2px 10px 5px}
.mirrored .chip{margin:0 9px 10px 2px}
.tag{position:absolute;z-index:2;font:400 12px/16px var(--overlay);padding:4px 9px 5px;border-radius:8px;background:var(--glass);border:1px solid var(--edge);white-space:nowrap;pointer-events:none}
.panel{background:var(--panel);border:1px solid var(--edge);border-radius:8px;padding:10px;display:grid;gap:8px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:4px;background:var(--tile);border-radius:8px;padding:10px 12px}
.tiles span{display:block;font-size:11px;color:var(--soft)}
.tiles b{font-size:16px}
.line{font-size:13px;line-height:17px;padding:0 6px}
.line span{font-size:12px;color:var(--soft)}
</style>
<main>
<header><h1>Sidetone Companions</h1><p>A session's subagents as small copies of its character, at the overlay's real size and speed. Start a few, finish one and watch it cheer and go. Rest the mouse on a small one to read its task.</p></header>
<div class="bar">
  <div class="group"><span>Subagents</span><button type="button" id="start">Start One</button><button type="button" id="finish">Finish One</button><button type="button" id="stop">Stop One</button><button type="button" id="run">Play a Run</button></div>
  <div class="group" id="styles" role="group" aria-label="Character"><span>Character</span></div>
  <div class="group"><button type="button" id="next">Next Figure</button></div>
  <div class="group" id="sessions" role="group" aria-label="The session itself"><span>Session</span></div>
  <div class="group" id="corners" role="group" aria-label="Corner"><span>Corner</span></div>
  <div class="group" id="sizes" role="group" aria-label="Size"><span>Size</span></div>
  <div class="group" id="behinds" role="group" aria-label="Behind it"><span>Behind It</span></div>
</div>
<p id="said" aria-live="polite"></p>
<div class="stage" id="stage"><div class="zoom"><div class="overlay" id="overlay">
  <div class="perch" id="perch"><canvas class="big" id="big" role="img" aria-label="The session's character"></canvas><span class="chip" id="chip" hidden></span></div>
  <div class="tag" id="tag" hidden></div>
  <div class="panel"><div class="tiles"><div><span>Context</span><b>56%</b></div><div><span>Total Tokens</span><b>310k</b></div><div><span>Total Time</span><b>48m</b></div><div><span>Tasks</span><b>3/5</b></div></div>
  <div class="line"><b id="name">api-server</b>&ensp;Fix the flaky login test<br><span>Running the tests</span></div></div>
</div></div></div>
<p class="note">Sizes, gaps and timing are the overlay's own: 88 and 44 px, 14 px between figures, twelve frames a second, a cheer of three seconds, a fade of a quarter second, three small ones and then a count. A stopped subagent goes without a cheer. The figures stand on a window you can see through, so what is behind them is your screen: try both backdrops.</p>
</main>
<script>
const DATA = __DATA__;
const L=DATA.layout, FPS=L.fps, ROWS=L.rows, CELL=L.cell, CHEER=DATA.cheer*1000, SHOWN=DATA.shown, FADE=250;
const TASKS=["Search the hooks","Read the overlay code","Check the tests","Measure the gaps","Review the wording","Update the notes"];
const el=id=>document.getElementById(id), perch=el("perch"), chip=el("chip"), tag=el("tag"), big=el("big");
let style=DATA.first, figure=1, session="working", mirrored=false, zoom=1, still=matchMedia("(prefers-reduced-motion: reduce)").matches;
let agents=[], small=[], made=0, count=0, bigSince=performance.now(), tagged=null, last=0;
const images={};
for(const s of Object.keys(DATA.styles))DATA.styles[s].forEach((f,i)=>{const im=new Image();im.src=f.file;images[s+i]=im});
const say=t=>{el("said").textContent=t};
function choice(parent,options,now,pick){options.forEach(([value,label])=>{const b=document.createElement("button");b.type="button";b.textContent=label;b.setAttribute("aria-pressed",value===now);
  b.onclick=()=>{parent.querySelectorAll("button").forEach(x=>x.setAttribute("aria-pressed","false"));b.setAttribute("aria-pressed","true");pick(value)};parent.append(b)})}
// The hub's side: which subagents run, which has just finished, the first three and how many more.
function start(){const a={id:++count,task:TASKS[(count-1)%TASKS.length],since:performance.now(),done:0};agents.push(a);say("Started: "+a.task);return a}
function finish(a){a=a||agents.find(x=>!x.done);if(!a||a.done||!agents.includes(a))return say("None is running.");a.done=performance.now();say("Finished: "+a.task+". It cheers for three seconds, then goes.")}
function stop(){const a=agents.find(x=>!x.done);if(!a)return say("None is running.");agents=agents.filter(x=>x!==a);say("Stopped: "+a.task+". It goes without a cheer.")}
function run(){agents=[];const three=[];[0,400,800].forEach((wait,i)=>setTimeout(()=>three[i]=start(),wait));[[2,4800],[1,9800],[0,14800]].forEach(([i,wait])=>setTimeout(()=>finish(three[i]),wait))}
function shown(now){agents=agents.filter(a=>!a.done||now-a.done<CHEER);return[agents.slice(0,SHOWN),Math.max(0,agents.length-SHOWN)]}
// The overlay's side: a small figure for each one named, fading in and away, the others closing up.
function fit(cv,size){const dpr=Math.min(3,devicePixelRatio||1);cv.width=cv.height=Math.round(size*dpr*zoom);cv.style.width=cv.style.height=size+"px"}
function make(a,now){const cv=document.createElement("canvas");cv.className="small";cv.tabIndex=0;cv.setAttribute("role","img");cv.setAttribute("aria-label","Subagent: "+a.task);fit(cv,44);
  const c={id:a.id,task:a.task,state:"working",since:now,lead:made++%3*.67,cv,born:a.since,gone:0};
  cv.onmouseenter=cv.onfocus=()=>point(c);cv.onmouseleave=cv.onblur=()=>point(null);
  perch.insertBefore(cv,chip);return c}
// How much of one shows: it fades in and away in a quarter second, and is dimmed while another is pointed at.
function alpha(c,now){let a=still?1:Math.min(1,(now-c.born)/FADE);if(c.gone)a=still?0:Math.min(a,1-(now-c.gone)/FADE);return Math.max(0,a)*(tagged&&tagged!==c?.45:1)}
function sync(now){const[want,more]=shown(now);
  for(const c of small){if(!c.gone&&!want.some(a=>a.id===c.id)){c.gone=now;if(tagged===c)point(null)}}
  for(const c of small.filter(c=>c.gone&&alpha(c,now)<=0)){c.cv.remove();small=small.filter(x=>x!==c);place()}
  for(const a of want){let c=small.find(x=>x.id===a.id&&!x.gone);if(!c){c=make(a,now);small.push(c)}const state=a.done?"done":"working";if(state!==c.state){c.state=state;c.since=now}}
  for(const c of small)c.cv.style.opacity=alpha(c,now);
  chip.textContent=more?"+"+more:"";chip.hidden=!more;perch.classList.toggle("has",small.length>0)}
function point(c){tagged=c;place()}
function place(){const first=small.find(c=>!c.gone);if(!tagged||tagged.gone||!first){tag.hidden=true;return}
  tag.textContent=tagged.task;tag.hidden=false;
  const o=el("overlay").getBoundingClientRect(),r=tagged.cv.getBoundingClientRect(),f=first.cv.getBoundingClientRect(),w=tag.offsetWidth,h=tag.offsetHeight;
  const x=(r.left-o.left)/zoom,s=r.width/zoom,middle=x+(s-w)/2,edge=(f.left-o.left)/zoom+(mirrored?s:0);
  tag.style.left=(mirrored?Math.min(middle,edge-w):Math.max(middle,edge))+"px";tag.style.top=((r.top-o.top)/zoom-h-2)+"px"}
function cellFor(moment,since,lead,now){if(still)return[ROWS[moment==="done"?"done_hold":moment][0],0];
  let a=(now-since)/1000+(moment==="working"?lead:0),row=moment;
  if(moment==="done"&&a*FPS>=ROWS.done[1]){row="done_hold";a-=ROWS.done[1]/FPS}
  const r=ROWS[row];return[r[0],Math.floor(a*FPS)%r[1]]}
function paint(cv,moment,since,lead,now){const f=DATA.styles[style][figure],im=images[style+figure];if(!im.complete||!im.naturalWidth)return;
  const[row,column]=cellFor(moment,since,lead,now),g=cv.getContext("2d");g.clearRect(0,0,cv.width,cv.height);g.imageSmoothingEnabled=f.cell>CELL;g.imageSmoothingQuality="high";
  cv.style.imageRendering=f.cell>CELL?"auto":"pixelated";g.drawImage(im,column*f.cell,row*f.cell,f.cell,f.cell,0,0,cv.width,cv.height)}
function draw(now,force){sync(now);if(!force&&now-last<1000/FPS-2)return;last=now;
  paint(big,session,bigSince,0,now);for(const c of small)paint(c.cv,c.state,c.since,c.lead,now)}
function tick(now){requestAnimationFrame(tick);draw(now,false)}
function look(){const f=DATA.styles[style][figure];el("name").style.color=f.color;big.setAttribute("aria-label","The session's character: "+f.name);fit(big,88);small.forEach(c=>fit(c.cv,44));draw(performance.now(),true);place()}
el("start").onclick=start;el("finish").onclick=()=>finish();el("stop").onclick=stop;el("run").onclick=run;
el("next").onclick=()=>{figure=(figure+1)%DATA.styles[style].length;look()};
choice(el("styles"),Object.keys(DATA.styles).map(s=>[s,DATA.names[s]]),style,s=>{style=s;figure=Math.min(figure,DATA.styles[s].length-1);look()});
choice(el("sessions"),[["working","Working"],["done","Done"],["idle","Idle"]],session,s=>{session=s;bigSince=performance.now()});
choice(el("corners"),[[false,"Right"],[true,"Left"]],mirrored,m=>{mirrored=m;perch.classList.toggle("mirrored",m);place()});
choice(el("sizes"),[[1,"Real Size"],[2,"Twice"]],zoom,z=>{zoom=z;el("stage").style.setProperty("--z",z);look()});
choice(el("behinds"),[["dark","Dark"],["light","Light"]],"dark",b=>el("stage").classList.toggle("light",b==="light"));
Object.values(images).forEach(im=>im.addEventListener("load",()=>draw(performance.now(),true)));
// It opens with three at work, started a moment apart as a real session starts them.
[1800,1400,1000].forEach(ago=>{start().since-=ago});say("Three subagents are running.");
look();requestAnimationFrame(tick);
</script>
"""


def main(out: str) -> None:
    os.makedirs(os.path.join(out, "sheets"), exist_ok=True)
    styles = {}
    for style in characters.STYLES:
        count = min(characters.kinds(style), SKETCHES) if style == "sketch" else characters.kinds(style)
        styles[style] = []
        for kind, color in enumerate(colors(count)):
            path = f"sheets/{style}-{kind}.png"
            with open(os.path.join(out, path), "wb") as f:
                f.write(characters.sheet(style, kind, color))
            styles[style].append({"file": path, "color": color, "name": NAMES[style][kind], "cell": characters.cell(style)})
    data = {"layout": characters.LAYOUT, "styles": styles, "names": LABELS, "first": "familiars",
            "cheer": base.AGENT_CHEER, "shown": base.AGENTS_SHOWN}
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(PAGE.replace("__DATA__", json.dumps(data)))
    print(os.path.join(out, "index.html"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "companions-page")
