"""The single-page web viewer served at '/'.

Kept as one self-contained string (no external assets, no web fonts) so it
works on an isolated/offline machine, which is the usual case for a security
appliance.
"""

VIEWER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Camera Monitor</title>
<style>
  :root{
    --bg:#0d1014; --panel:#141920; --panel-2:#10151b; --line:#222c37;
    --ink:#c9d4df; --muted:#6c7886; --muted-2:#475260;
    --signal:#ffb01f;            /* live / alert */
    --data:#54d6c4;              /* telemetry values */
    --ok:#54d6c4; --bad:#ff5d52; --idle:#475260;
    --mono:ui-monospace,"SF Mono","Cascadia Mono",Consolas,"Roboto Mono",monospace;
    --sans:ui-sans-serif,system-ui,"Segoe UI",Inter,Roboto,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{
    margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
    -webkit-font-smoothing:antialiased; display:flex; flex-direction:column;
  }

  /* ---- top status strip ---- */
  header{
    display:flex; align-items:center; gap:18px; padding:11px 18px;
    border-bottom:1px solid var(--line); background:var(--panel-2);
  }
  .brand{display:flex; align-items:baseline; gap:10px; min-width:0}
  .brand .id{
    font-family:var(--mono); font-weight:600; letter-spacing:.14em;
    font-size:15px; color:var(--ink);
  }
  .brand .sub{font-size:11px; color:var(--muted); letter-spacing:.22em; text-transform:uppercase}
  .rec{display:flex; align-items:center; gap:8px; margin-left:auto; font-family:var(--mono); font-size:12px; letter-spacing:.18em}
  .dot{width:9px; height:9px; border-radius:50%; background:var(--idle); box-shadow:0 0 0 0 rgba(255,176,31,.6)}
  .rec.live .dot{background:var(--signal); animation:pulse 1.6s ease-out infinite}
  .rec.live .lbl{color:var(--signal)}
  .rec .lbl{color:var(--muted)}
  .clock{font-family:var(--mono); font-size:12px; color:var(--muted); letter-spacing:.08em; padding-left:18px; border-left:1px solid var(--line)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,176,31,.55)}70%{box-shadow:0 0 0 7px rgba(255,176,31,0)}100%{box-shadow:0 0 0 0 rgba(255,176,31,0)}}
  @media (prefers-reduced-motion:reduce){.rec.live .dot{animation:none}}

  /* ---- main layout ---- */
  main{flex:1; display:grid; grid-template-columns:1fr 268px; min-height:0}
  .stage{position:relative; display:flex; align-items:center; justify-content:center; padding:20px; min-width:0; min-height:0; background:
      radial-gradient(120% 120% at 50% 0%, #11161d 0%, var(--bg) 70%);}
  .frame{position:relative; max-width:100%; max-height:100%; line-height:0}
  .frame img{display:block; max-width:100%; max-height:calc(100vh - 140px); background:#000; border:1px solid var(--line)}
  /* viewfinder reticle */
  .frame .bracket{position:absolute; width:22px; height:22px; border:2px solid var(--signal); opacity:.85; pointer-events:none}
  .frame .tl{top:-1px; left:-1px; border-right:0; border-bottom:0}
  .frame .tr{top:-1px; right:-1px; border-left:0; border-bottom:0}
  .frame .bl{bottom:-1px; left:-1px; border-right:0; border-top:0}
  .frame .br{bottom:-1px; right:-1px; border-left:0; border-top:0}
  .stamp{position:absolute; left:8px; bottom:8px; font-family:var(--mono); font-size:11px;
    color:#e8eef4; background:rgba(0,0,0,.45); padding:2px 7px; letter-spacing:.06em; pointer-events:none}

  .lost{position:absolute; inset:20px; display:none; align-items:center; justify-content:center;
    background:rgba(8,10,13,.78); border:1px solid var(--bad)}
  .lost.on{display:flex}
  .lost span{font-family:var(--mono); letter-spacing:.3em; color:var(--bad); font-size:13px}

  /* ---- telemetry rail ---- */
  aside{border-left:1px solid var(--line); background:var(--panel); display:flex; flex-direction:column}
  .rail-h{padding:13px 16px 9px; font-family:var(--mono); font-size:10px; letter-spacing:.26em; text-transform:uppercase; color:var(--muted)}
  .readouts{padding:2px 16px 14px}
  .ro{display:flex; align-items:baseline; justify-content:space-between; gap:10px; padding:9px 0; border-bottom:1px solid var(--line)}
  .ro:last-child{border-bottom:0}
  .ro .k{font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--muted)}
  .ro .v{font-family:var(--mono); font-size:13px; color:var(--data); text-align:right}
  .ro .v.state{display:inline-flex; align-items:center; gap:7px}
  .pip{width:8px; height:8px; border-radius:50%; background:var(--idle)}
  .pip.ok{background:var(--ok)} .pip.bad{background:var(--bad)} .pip.idle{background:var(--idle)}
  .v.muted{color:var(--muted-2)}

  .controls{margin-top:auto; padding:14px 16px; border-top:1px solid var(--line); display:grid; gap:8px}
  button,.btn{
    appearance:none; font-family:var(--mono); font-size:12px; letter-spacing:.1em; text-transform:uppercase;
    color:var(--ink); background:var(--panel-2); border:1px solid var(--line); padding:9px 11px; cursor:pointer;
    text-align:left; transition:border-color .12s, color .12s;
  }
  button:hover,.btn:hover{border-color:var(--data); color:#fff}
  button:focus-visible,.btn:focus-visible{outline:2px solid var(--data); outline-offset:2px}
  button[aria-pressed="true"]{border-color:var(--signal); color:var(--signal)}

  @media (max-width:860px){
    main{grid-template-columns:1fr}
    aside{border-left:0; border-top:1px solid var(--line)}
    .frame img{max-height:60vh}
    .clock{display:none}
  }
</style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="id" id="camLabel">CAM-01</span>
      <span class="sub">security&nbsp;monitor</span>
    </div>
    <div class="rec" id="rec"><span class="dot"></span><span class="lbl">OFFLINE</span></div>
    <div class="clock" id="clock">--:--:--</div>
  </header>

  <main>
    <section class="stage">
      <div class="frame">
        <span class="bracket tl"></span><span class="bracket tr"></span>
        <span class="bracket bl"></span><span class="bracket br"></span>
        <img id="feed" alt="Live camera feed" />
        <div class="stamp" id="stamp"></div>
        <div class="lost" id="lost"><span>SIGNAL&nbsp;LOST</span></div>
      </div>
    </section>

    <aside>
      <div class="rail-h">Telemetry</div>
      <div class="readouts">
        <div class="ro"><span class="k">Source</span><span class="v" id="t-source">--</span></div>
        <div class="ro"><span class="k">Resolution</span><span class="v" id="t-res">--</span></div>
        <div class="ro"><span class="k">Capture</span><span class="v" id="t-fps">-- fps</span></div>
        <div class="ro"><span class="k">Viewers</span><span class="v" id="t-viewers">0</span></div>
        <div class="ro"><span class="k">Virtual cam</span><span class="v state" id="t-vcam"><span class="pip idle"></span>--</span></div>
        <div class="ro"><span class="k">RTSP</span><span class="v state" id="t-rtsp"><span class="pip idle"></span>--</span></div>
        <div class="ro"><span class="k">Uptime</span><span class="v" id="t-uptime">--</span></div>
      </div>
      <div class="controls">
        <button id="btnMode" aria-pressed="false">Transport: MJPEG</button>
        <a class="btn" id="btnSnap" href="/snapshot.jpg" download>Save snapshot</a>
        <button id="btnFull">Fullscreen</button>
      </div>
    </aside>
  </main>

<script>
(function(){
  const feed = document.getElementById('feed');
  const stamp = document.getElementById('stamp');
  const lost = document.getElementById('lost');
  const rec = document.getElementById('rec');
  const recLbl = rec.querySelector('.lbl');

  let useWS = false, ws = null, lastObjUrl = null, lastFrameTs = 0, lastConnected = null;

  function startMJPEG(){
    if (ws){ try{ws.close();}catch(e){} ws=null; }
    feed.src = '/stream.mjpg?ts=' + Date.now();
    feed.onload = () => { lastFrameTs = Date.now(); };
  }
  function startWS(){
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(proto + '://' + location.host + '/ws');
    ws.binaryType = 'blob';
    ws.onmessage = (ev) => {
      const url = URL.createObjectURL(ev.data);
      feed.src = url;
      if (lastObjUrl) URL.revokeObjectURL(lastObjUrl);
      lastObjUrl = url;
      lastFrameTs = Date.now();
    };
    ws.onclose = () => { if (useWS) setTimeout(startWS, 1500); };
  }
  function setMode(ws_on){
    useWS = ws_on;
    lastFrameTs = 0;
    const b = document.getElementById('btnMode');
    b.textContent = 'Transport: ' + (ws_on ? 'WebSocket' : 'MJPEG');
    b.setAttribute('aria-pressed', ws_on ? 'true' : 'false');
    if (ws_on) startWS(); else startMJPEG();
  }
  document.getElementById('btnMode').addEventListener('click', () => setMode(!useWS));
  document.getElementById('btnFull').addEventListener('click', () => {
    const el = document.querySelector('.frame');
    if (!document.fullscreenElement) el.requestFullscreen && el.requestFullscreen();
    else document.exitFullscreen();
  });

  // live clock + overlay timestamp
  function pad(n){ return String(n).padStart(2,'0'); }
  function tick(){
    const d = new Date();
    const t = pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
    document.getElementById('clock').textContent = t;
    stamp.textContent = d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+'  '+t;
    // "lost" if the server reports disconnected, or (WS only) frames stalled >4s
    const wsStall = useWS && lastFrameTs && (Date.now() - lastFrameTs > 4000);
    lost.classList.toggle('on', wsStall || lastConnected === false);
  }
  setInterval(tick, 1000); tick();

  function fmtUptime(s){
    s = Math.floor(s||0);
    const h = Math.floor(s/3600), m = Math.floor((s%3600)/60), sec = s%60;
    return (h? h+'h ':'') + pad(m)+'m '+pad(sec)+'s';
  }
  function setState(el, info){
    const pip = el.querySelector('.pip');
    let cls='idle', txt='off';
    if (info && info.enabled){
      if (info.active){ cls='ok'; txt='active'; }
      else { cls='bad'; txt = info.error ? 'error' : 'starting'; }
    }
    pip.className = 'pip ' + cls;
    el.lastChild.textContent = txt;
    if (info && info.error) el.title = info.error;
  }

  async function poll(){
    try{
      const r = await fetch('/status', {cache:'no-store'});
      const s = await r.json();
      document.getElementById('camLabel').textContent = s.label || 'CAM';
      document.getElementById('t-source').textContent = s.source;
      document.getElementById('t-res').textContent = s.connected ? (s.width+'x'+s.height) : '--';
      document.getElementById('t-fps').textContent = (s.measured_fps!=null? s.measured_fps.toFixed(1):'--') + ' fps';
      document.getElementById('t-viewers').textContent = s.viewers;
      document.getElementById('t-uptime').textContent = fmtUptime(s.uptime);
      setState(document.getElementById('t-vcam'), s.virtual_camera);
      setState(document.getElementById('t-rtsp'), s.rtsp);

      const live = !!s.connected;
      lastConnected = live;
      rec.classList.toggle('live', live);
      recLbl.textContent = live ? 'LIVE' : 'OFFLINE';
    }catch(e){
      lastConnected = false;
      rec.classList.remove('live'); recLbl.textContent='OFFLINE';
    }
  }
  setInterval(poll, 1500); poll();

  setMode(false);  // start in MJPEG
})();
</script>
</body>
</html>
"""
