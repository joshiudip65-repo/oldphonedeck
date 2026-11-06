const $ = (id) => document.getElementById(id);
const hist = [];           // net down samples for sparkline
let buttonsRendered = false;

function post(url, body) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }).catch(() => {});
}

function renderButtons(buttons) {
  const g = $("buttons");
  g.innerHTML = "";
  buttons.forEach((b) => {
    const el = document.createElement("div");
    el.className = "btn";
    el.innerHTML = `<span class="ico">${b.icon || "▣"}</span><span class="lbl">${b.label}</span>`;
    el.addEventListener("click", () => {
      el.animate([{ transform: "scale(.9)" }, { transform: "scale(1)" }], { duration: 120 });
      if (navigator.vibrate) navigator.vibrate(8);
      post("/api/action", { id: b.id });
    });
    g.appendChild(el);
  });
  buttonsRendered = true;
}

function clock() {
  const d = new Date();
  $("time").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("date").textContent = d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
}

function sparkline() {
  if (hist.length < 2) return;
  const max = Math.max(1, ...hist);
  const n = hist.length;
  const pts = hist.map((v, i) => {
    const x = (i / (n - 1)) * 160;
    const y = 34 - (v / max) * 32;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  $("sparkline").setAttribute("points", pts.join(" "));
}

function battMeter(pct) {
  const cls = pct <= 10 ? "crit" : pct <= 25 ? "low" : "";
  return `<div class="meter"><i class="${cls}" style="width:${pct}%"></i></div>`;
}

function renderBatteries(s) {
  const rows = [];
  if (s.battery != null) {
    const label = s.charging ? "Mac ⚡" : "Mac";
    rows.push({ name: label, pct: s.battery });
  }
  (s.bt || []).forEach((b) => rows.push(b));
  $("battlist").innerHTML = rows.map((r) =>
    `<div class="batt-row"><span class="nm">${r.name}</span>${battMeter(r.pct)}<span class="pc">${r.pct}%</span></div>`
  ).join("") || `<div class="batt-row"><span class="nm" style="color:var(--dim)">No devices</span></div>`;
}

function renderPlayer(np) {
  const p = $("player");
  if (!np) { p.classList.add("hidden"); return; }
  p.classList.remove("hidden");
  $("trackname").textContent = np.track;
  $("artist").textContent = np.artist;
  $("playbtn").textContent = np.playing ? "⏸" : "▶";
  const pct = np.dur ? Math.min(100, (np.pos / np.dur) * 100) : 0;
  $("progress").style.width = pct + "%";
}

async function tick() {
  try {
    const s = await (await fetch("/api/stats")).json();
    if (!buttonsRendered && s.buttons) renderButtons(s.buttons);
    $("host").textContent = s.mac_name || "Mac";
    $("down").textContent = s.net.down.toFixed(1);
    $("up").textContent = s.net.up.toFixed(1);
    $("ping").textContent = s.net.ping != null ? s.net.ping + " ms" : "— ms";
    hist.push(s.net.down); if (hist.length > 40) hist.shift();
    sparkline();
    renderBatteries(s);
    renderPlayer(s.now_playing);
  } catch (e) { /* server not ready yet */ }
}

document.querySelectorAll("#player .controls button").forEach((b) =>
  b.addEventListener("click", () => {
    if (navigator.vibrate) navigator.vibrate(8);
    post("/api/media", { cmd: b.dataset.cmd }).then(() => setTimeout(tick, 250));
  })
);

// Keep the screen awake while docked (supported on Chrome/Android).
async function keepAwake() {
  try { if ("wakeLock" in navigator) await navigator.wakeLock.request("screen"); } catch (e) {}
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) keepAwake(); });

clock(); setInterval(clock, 1000);
tick(); setInterval(tick, 2000);
keepAwake();
