#!/usr/bin/env python3
"""Build the offline presentation and SVG using only the Python standard library."""
from pathlib import Path
from html import escape
import json

OUT = Path(__file__).resolve().parent
CORAL, CYAN, PURPLE, GREEN = '#ff947f', '#6be4dc', '#b5a1ff', '#b4e68a'
parts = ['''<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1020" viewBox="0 0 1600 1020" role="img" aria-labelledby="title desc">
<title id="title">WannaCry incident lab — architecture and incident flow</title>
<desc id="desc">An attacker delivers a public key to the victim inbox. Five fixture documents are encrypted locally. The victim pays exactly one lab ETH to RansomExchange on a private Ethereum chain. The attacker posts a sealed reply; the victim retrieves it and recovers the documents locally. Supporting infrastructure includes a faucet, utility server, and SEED map.</desc>
<defs><pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#243248" opacity=".45"/></pattern>''']
for name, color in [('coral',CORAL),('cyan',CYAN),('purple',PURPLE),('green',GREEN)]:
    parts.append(f'<marker id="{name}" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M1 1 L8 5 L1 9" fill="none" stroke="{color}" stroke-width="1.5"/></marker>')
parts += ['</defs><rect width="1600" height="1020" rx="24" fill="#0b1220"/><rect width="1600" height="1020" fill="url(#grid)"/>', '<g font-family="DejaVu Sans,Arial,sans-serif">']
def txt(x,y,s,size=18,color='#e9eef7',weight='400',anchor='start'):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')
def rect(x,y,w,h,fill='#121e30',stroke='#2a384f',r=16):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}"/>')
txt(64,51,'SEED EMULATOR  /  YESTERDAY ONCE MORE',14,CYAN,'600')
txt(64,105,'WannaCry, from delivery to recovery.',40,weight='700')
txt(64,140,'Two human roles. One on-chain exchange. Five documents restored.',19,'#a4b3ca')
rect(1280,42,256,40,fill='#152337',r=20)
txt(1408,68,'PRIVATE LAB  ·  AS180',14,'#c4d1e4','600','middle')
actors=[(64,'01  /  ATTACKER','host_1', '10.180.0.72',CORAL,
         ['Deliver the public key · watch requests','Post sealed replies · withdraw funds'], 'RSA private key stays on this host.'),
        (576,'02  /  VICTIM','host_0', '10.180.0.71',CYAN,
         ['Delivery inbox :4450 · participant menu','Five documents · encrypted wallet'], 'File key and recovery stay local.'),
        (1088,'03  /  EXCHANGE','RansomExchange', 'Ethereum PoA · chain ID 18000',PURPLE,
         ['registerVictim: exactly 1 lab ETH','submitReply: attacker identity only'], 'Only opaque sealed key material on-chain.')]
for x,label,name,addr,color,lines,note in actors:
    rect(x,183,448,188)
    parts.append(f'<rect x="{x+1}" y="200" width="3" height="33" rx="1" fill="{color}"/>')
    txt(x+24,214,label,13,color,'700'); txt(x+24,249,name,27,weight='700')
    txt(x+24,276,addr,16,'#a4b3ca')
    for i,line in enumerate(lines): txt(x+24,307+i*25,line,16)
    txt(x+24,353,note,13,color)
for x in (288,800,1312):
    parts.append(f'<path d="M{x} 385 V795" stroke="#304057" stroke-width="2" stroke-dasharray="4 9"/>')
steps=[
 ('Deliver', 'The attacker sends its public key to wormdoor.py at POST /drop. This inbox stands in for worm delivery; it does not simulate an exploit.', 'host_1 → host_0 · delivery inbox :4450'),
 ('Encrypt', 'The victim runs the payload locally. Five generated documents become .WNCRY envelopes and their plaintext originals are removed.', 'host_0 · RSA-2048 + AES-256-GCM'),
 ('Pay', 'The victim creates a wallet, gets lab ETH through the SEED Exchange menu, and signs registerVictim with exactly 1 lab ETH. The wallet key signs transactions only.', 'host_0 → RansomExchange · signed payment + sealed request'),
 ('Reply', 'The attacker watches on-chain requests and posts victim_priv sealed for the victim’s ephemeral X25519 key. The attacker’s RSA private key stays on host_1.', 'host_1 → RansomExchange · attacker-authorized sealed reply'),
 ('Recover', 'The victim polls getReply, opens the sealed reply, unseals its file key locally, and restores all five documents. Every recovered file is checked against its original SHA-256 baseline.', 'RansomExchange → host_0 · read reply, then recover locally')]
def flow(n,y,x1,x2,label,detail,color,marker,local=False):
    parts.append(f'<g class="step" data-step="{n}">')
    rect(64,y-38,38,32,fill='#172438',stroke=color,r=9);txt(83,y-16,f'{n:02}',14,color,'700','middle')
    if local:
        parts.append(f'<path d="M800 {y} H956 V{y+20} H800" fill="none" stroke="{color}" stroke-width="2.5" marker-end="url(#{marker})"/>')
        tx=980;anchor='start'
    else:
        parts.append(f'<path d="M{x1} {y} H{x2}" stroke="{color}" stroke-width="2.5" marker-end="url(#{marker})"/>')
        tx=(x1+x2)/2;anchor='middle'
    txt(tx,y-15,label,18,color,'600',anchor)
    txt(tx,y+43 if local else y+27,detail,14,'#a4b3ca','400',anchor)
    for x in {x1,x2}: parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>')
    parts.append('</g>')
flow(1,425,288,800,'Deliver public key','Manual courier → wormdoor.py',CORAL,'coral')
flow(2,501,800,800,'Encrypt locally','5 documents → .WNCRY',CYAN,'cyan',True)
flow(3,582,800,1312,'Pay 1 lab ETH','Signed request + sealed bytes',PURPLE,'purple')
flow(4,663,288,1312,'Post sealed reply','watch → submitReply · victim private key sealed for its recipient',CORAL,'coral')
flow(5,744,1312,800,'Read reply → recover locally','5 originals restored · SHA-256 verified',GREEN,'green')
rect(64,819,1472,107,fill='#101b2c')
txt(88,847,'SUPPORTING INFRASTRUCTURE',12,'#7f94b3','700')
for x,title,detail in [(88,'Docker host + SEED map','Build / control · localhost:8080'),(455,'3 Geth signers','10.180.0.81–83 · RPC .83:8545'),(822,'Faucet','10.180.0.90 · lab ETH'),(1189,'Utility server','10.180.0.95:8080 · deployment')]:
    txt(x,878,title,17,weight='600'); txt(x,904,detail,14,'#a4b3ca')
txt(64,961,'KEY HIERARCHY',12,CYAN,'700')
txt(214,961,'Attacker private key → victim private key → file key → documents',17)
txt(64,994,'Network: 10.180.0.0/24 · router0 .254     /     SEED Exchange is a faucet facade     /     Controlled five-fixture demonstration',13,'#7f94b3')
parts.append('</g></svg>')
svg='\n'.join(parts)
(OUT/'architecture.svg').write_text(svg)
html='''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WannaCry Lab · Architecture walkthrough</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#080e18;color:#e9eef7;font-family:system-ui,sans-serif}main{max-width:1440px;margin:auto;padding:20px 28px}header{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:14px}.eyebrow{font-size:12px;letter-spacing:.15em;color:#6be4dc}button{background:#162337;color:#dbe6f6;border:1px solid #34455e;border-radius:9px;padding:10px 15px;cursor:pointer;font:inherit;font-size:13px}button:hover,button:focus-visible{border-color:#6be4dc}button[aria-pressed="true"]{background:#254544;border-color:#6be4dc}button:disabled{opacity:.35;cursor:default}.controls{display:flex;gap:8px;flex-wrap:wrap}svg{display:block;width:100%;height:auto;max-height:calc(100vh - 215px)}.step{transition:opacity .25s}.focused .step{opacity:.16}.focused .step.active{opacity:1}.caption{display:grid;grid-template-columns:180px 1fr;gap:24px;margin:18px 0 10px;padding:18px 22px;border:1px solid #293950;border-radius:12px;background:#101b2c;min-height:106px}.caption h1{font-size:20px;margin:0 0 6px}.caption p{margin:0;color:#b2c1d8;font-size:15px;line-height:1.55}.meta{font-size:12px;color:#6be4dc;margin-top:8px}footer{color:#7f94b3;font-size:12px;display:flex;justify-content:space-between;gap:16px}a{color:#a4b3ca}@media(max-width:700px){main{padding:12px}header{align-items:flex-start;flex-direction:column}.caption{grid-template-columns:1fr;gap:8px}svg{max-height:none}footer{flex-wrap:wrap}}@media(prefers-reduced-motion:reduce){.step{transition:none}}@media print{header,footer{display:none}main{padding:0}svg{max-height:none}.caption{display:none}.step{opacity:1!important}}
</style>
<main><header><div class="eyebrow">ARCHITECTURE / PRESENTER VIEW</div><div class="controls"><button id="overview" aria-pressed="true">Overview</button><button id="prev" aria-label="Previous step">← Previous</button><button id="next">Start walkthrough →</button><button id="full">Fullscreen</button></div></header>
<div id="diagram">__SVG__</div>
<section class="caption" aria-live="polite"><div><h1 id="heading">The complete incident</h1><div id="counter" class="meta">OVERVIEW · 5 STAGES</div></div><div><p id="description">Follow the exchange from public-key delivery to verified document recovery. Use the arrow keys or the controls above to walk your audience through each stage.</p><div class="meta" id="detail">Architecture walkthrough · illustrative, not connected to a running lab</div></div></section>
<footer><span>← / → navigate · O overview · F fullscreen</span><span><a href="architecture.svg" download>Download SVG</a> · <a href="architecture.png" download>Download PNG</a></span></footer></main>
<script>
const steps=__STEPS__;let current=0;const el=id=>document.getElementById(id);
function show(n){current=Math.max(0,Math.min(5,n));el('diagram').classList.toggle('focused',current>0);document.querySelectorAll('.step').forEach(g=>g.classList.toggle('active',Number(g.dataset.step)===current));el('overview').setAttribute('aria-pressed',String(current===0));el('prev').disabled=current===0;el('next').disabled=current===5;el('next').textContent=current===0?'Start walkthrough →':'Next →';el('heading').textContent=current?steps[current-1][0]:'The complete incident';el('counter').textContent=current?`STAGE ${current} OF 5`:'OVERVIEW · 5 STAGES';el('description').textContent=current?steps[current-1][1]:'Follow the exchange from public-key delivery to verified document recovery. Use the arrow keys or the controls above to walk your audience through each stage.';el('detail').textContent=current?steps[current-1][2]:'Architecture walkthrough · illustrative, not connected to a running lab';}
async function full(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{el('detail').textContent='Fullscreen unavailable here. Open this file directly in a browser or use its fullscreen command.';}}
el('overview').onclick=()=>show(0);el('prev').onclick=()=>show(current-1);el('next').onclick=()=>show(current+1);el('full').onclick=full;
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey||e.target.closest('button,a,input,textarea,select'))return;if(['ArrowRight','ArrowLeft','o','O','f','F'].includes(e.key))e.preventDefault();if(e.key==='ArrowRight')show(current+1);if(e.key==='ArrowLeft')show(current-1);if(e.key.toLowerCase()==='o')show(0);if(e.key.toLowerCase()==='f')full();});show(0);
</script></html>'''
(OUT/'architecture.html').write_text(html.replace('__SVG__',svg).replace('__STEPS__',json.dumps(steps)))
print('Generated architecture.svg and architecture.html')
