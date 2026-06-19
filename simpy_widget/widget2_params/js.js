/* ======================================================
   SimPy Line 2 — Config Parameters Viewer
   ThingsBoard static widget

   Fetches configs from GET /configs and displays:
     - Source2: inter_arrival_time_mean
     - PdM1/PdM2 processors: cycle_time + sensor ranges
     - Final processor: cycle_time

   SETTINGS:
     serverBaseUrl  — e.g. http://localhost:9000
   ====================================================== */

let _healthTimer = null;

const st2 = {
  BASE: "http://localhost:9000",
};

/* ── DOM ──────────────────────────────────────────────── */
function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

/* ── Settings ─────────────────────────────────────────── */
const LS_KEY = "simpy_widget_settings";

function getTop() {
  try {
    return window.top || window;
  } catch (_) {
    return window;
  }
}
function getMem() {
  const t = getTop();
  if (!t._spw) t._spw = {};
  return t._spw;
}
function getLS() {
  try {
    const l = getTop().localStorage;
    l.getItem("_");
    return l;
  } catch (_) {}
  try {
    const l = window.localStorage;
    l.getItem("_");
    return l;
  } catch (_) {}
  return null;
}
function storeRead() {
  const m = getMem();
  if (m.serverBaseUrl) return m;
  const ls = getLS();
  if (ls) {
    try {
      const d = JSON.parse(ls.getItem(LS_KEY) || "{}");
      if (d.serverBaseUrl) return d;
    } catch (_) {}
  }
  return {};
}
function storeWrite(obj) {
  Object.assign(getMem(), obj);
  const ls = getLS();
  if (ls) {
    try {
      ls.setItem(LS_KEY, JSON.stringify(Object.assign({}, getMem(), obj)));
    } catch (_) {}
  }
}
function loadSettings() {
  const s = self.ctx.settings || {};
  const stored = storeRead();
  st2.BASE = (
    stored.serverBaseUrl ||
    s.serverBaseUrl ||
    "http://localhost:9000"
  ).replace(/\/+$/, "");
}
function openSettings() {
  $q("#cfgUrl").value = st2.BASE;
  $q("#settingsModal").style.display = "flex";
}
function closeSettings() {
  $q("#settingsModal").style.display = "none";
}
function saveSettings() {
  const url = ($q("#cfgUrl").value || "").replace(/\/+$/, "").trim();
  if (!url) return;
  st2.BASE = url;
  storeWrite({ serverBaseUrl: url });
  closeSettings();
  setStatus("Settings saved — " + url, "ok");
  checkHealth();
  loadConfigs();
}

/* ── Status ───────────────────────────────────────────── */
function setStatus(msg, level) {
  const el = $q("#statusBar");
  if (!el) return;
  el.textContent = msg;
  el.className = "sp2-status" + (level ? " " + level : "");
}

/* ── Health ───────────────────────────────────────────── */
async function checkHealth() {
  const dot = $q("#healthDot"),
    text = $q("#healthText");
  try {
    const r = await fetch(st2.BASE + "/health", {
      signal: AbortSignal.timeout(4000),
    });
    const ok = r.ok;
    if (dot) dot.className = "sp2-dot " + (ok ? "ok" : "err");
    if (text) text.textContent = ok ? "API connected" : "API error " + r.status;
  } catch (_) {
    if (dot) dot.className = "sp2-dot err";
    if (text) text.textContent = "Unreachable";
  }
}

/* ── Config fetch & render ─────────────────────────────── */

// Names we care about, in display order
const LINE2_OBJECTS = ["source2", "pdm1_proc", "pdm2_proc", "final_proc"];

async function loadConfigs() {
  setStatus("Loading configs…");
  try {
    const r = await fetch(st2.BASE + "/configs?limit=100", {
      signal: AbortSignal.timeout(6000),
    });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const all = await r.json();

    // Index by name
    const byName = {};
    for (const c of all) byName[c.name] = c;

    renderSource(byName["source2"]);
    renderProcessors(byName);
    renderSensors(byName);

    setStatus(
      "Loaded " + all.length + " configs — showing Line 2 objects",
      "ok",
    );
  } catch (e) {
    setStatus("Error loading configs: " + e.message, "err");
  }
}

/* ── Source table ─────────────────────────────────────── */
function renderSource(cfg) {
  const tbody = $q("#sourceTbody");
  if (!cfg) {
    tbody.innerHTML =
      "<tr><td colspan='4' style='color:#bbb'>source2 not found in DB</td></tr>";
    return;
  }
  const d = cfg.data || {};
  tbody.innerHTML = `
    <tr>
      <td class="sp2-name">source2</td>
      <td class="sp2-param">Inter-arrival time mean</td>
      <td class="sp2-val">${fmt(d.inter_arrival_time_mean)}</td>
      <td>s</td>
    </tr>
    <tr>
      <td></td>
      <td class="sp2-param">Distribution</td>
      <td>${esc(d.distribution || "exponential")}</td>
      <td></td>
    </tr>
  `;
}

/* ── Processors table ─────────────────────────────────── */
function renderProcessors(byName) {
  const tbody = $q("#procTbody");
  const rows = [];

  for (const name of ["pdm1_proc", "pdm2_proc", "final_proc"]) {
    const cfg = byName[name];
    if (!cfg) {
      rows.push(
        `<tr><td class="sp2-name">${name}</td><td colspan='3' style='color:#bbb'>not found in DB</td></tr>`,
      );
      continue;
    }
    const d = cfg.data || {};
    rows.push(`
      <tr>
        <td class="sp2-name">${esc(name)}</td>
        <td class="sp2-param">Cycle time</td>
        <td class="sp2-val">${fmt(d.cycle_time)}</td>
        <td>s</td>
      </tr>
    `);
  }

  tbody.innerHTML = rows.join("");
}

/* ── Sensors table ────────────────────────────────────── */
function renderSensors(byName) {
  const tbody = $q("#sensorTbody");
  const rows = [];

  for (const [machineKey, machineName] of [
    ["pdm1_proc", "PdM1"],
    ["pdm2_proc", "PdM2"],
  ]) {
    const cfg = byName[machineKey];
    if (!cfg) {
      rows.push(
        `<tr><td class="sp2-name">${machineName}</td><td colspan='5' style='color:#bbb'>not found in DB</td></tr>`,
      );
      continue;
    }
    const sensors = cfg.data.sensors || {};
    const entries = Object.entries(sensors);

    entries.forEach(([sensorName, s], i) => {
      rows.push(`
        <tr>
          ${i === 0 ? `<td class="sp2-machine-cell sp2-name" rowspan="${entries.length}">${machineName}</td>` : ""}
          <td class="sp2-param">${esc(sensorName)}</td>
          <td class="sp2-val">${fmt(s.min)}</td>
          <td class="sp2-val">${fmt(s.max)}</td>
          <td>${esc(s.unit || "—")}</td>
          <td>${esc(s.distribution || "uniform")}</td>
        </tr>
      `);
    });
  }

  tbody.innerHTML = rows.join("");
}

function isDark() {
  return !!document
    .querySelector(".tb-dashboard-page")
    ?.classList.contains("dark");
}

function applyTheme() {
  const root = $q(".sp2-root");
  if (root) root.classList.toggle("dark", isDark());
}

function fmt(v, decimals) {
  if (v === undefined || v === null) return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return String(v);
  return decimals !== undefined ? n.toFixed(decimals) : n.toLocaleString();
}
function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ── Lifecycle ─────────────────────────────────────────── */
self.onInit = function () {
  loadSettings();
  applyTheme();

  $q("#refreshBtn").onclick = loadConfigs;
  $q("#settingsBtn").onclick = openSettings;
  $q("#cfgCancel").onclick = closeSettings;
  $q("#cfgSave").onclick = saveSettings;

  checkHealth();
  loadConfigs();
  _healthTimer = setInterval(checkHealth, 15000);
};

self.onDestroy = function () {
  if (_healthTimer) clearInterval(_healthTimer);
};
