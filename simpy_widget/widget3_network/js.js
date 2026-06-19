/* ======================================================
   SimPy — Simulation Network Editor
   ThingsBoard static widget

   Networks are stored as Config records in config-api.
   Each network record has data._type === "network" so
   the widget can list only network configs and ignore
   sim-object configs (source2, pdm1_proc, etc.).

   RESOURCES required:
     https://cdn.jsdelivr.net/npm/litegraph.js@0.7.18/build/litegraph.js

   SETTINGS:
     serverBaseUrl  — e.g. http://localhost:9000
   ====================================================== */

/* Inject litegraph CSS */
(function () {
  if (document.querySelector("link[data-litegraph]")) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = "https://cdn.jsdelivr.net/npm/litegraph.js@0.7.18/css/litegraph.css";
  l.setAttribute("data-litegraph", "1");
  document.head.appendChild(l);
})();

const LS_KEY = "simpy_widget_settings";

let _graph = null;
let _lgCanvas = null;
let _healthTimer = null;
let _activeId = null; // DB id of currently loaded network config
let _activeName = null;

const snSt = { BASE: "http://localhost:9000" };

/* ── DOM ───────────────────────────────────────────────────── */
function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

/* ── Settings ──────────────────────────────────────────────── */
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
  const s = self.ctx.settings || {},
    stored = storeRead();
  snSt.BASE = (
    stored.serverBaseUrl ||
    s.serverBaseUrl ||
    "http://localhost:9000"
  ).replace(/\/+$/, "");
}
function openSettings() {
  $q("#cfgUrl").value = snSt.BASE;
  $q("#settingsModal").style.display = "flex";
}
function closeSettings() {
  $q("#settingsModal").style.display = "none";
}
function saveSettings() {
  const url = ($q("#cfgUrl").value || "").replace(/\/+$/, "").trim();
  snSt.BASE = url;
  storeWrite({ serverBaseUrl: url });
  closeSettings();
  setStatus("Settings saved", "ok");
  checkHealth();
  refreshNetList();
}

/* ── Status ────────────────────────────────────────────────── */
function setStatus(msg, level) {
  const el = $q("#statusBar");
  if (!el) return;
  el.textContent = msg;
  el.className = "sn-status" + (level ? " " + level : "");
}

/* ── Health ────────────────────────────────────────────────── */
async function checkHealth() {
  const dot = $q("#healthDot"),
    text = $q("#healthText");
  try {
    const r = await fetch(snSt.BASE + "/health", {
      signal: AbortSignal.timeout(4000),
    });
    const ok = r.ok;
    if (dot) dot.className = "sn-dot " + (ok ? "ok" : "err");
    if (text) text.textContent = ok ? "API connected" : "API error " + r.status;
  } catch (_) {
    if (dot) dot.className = "sn-dot err";
    if (text) text.textContent = "Unreachable";
  }
}

/* ── API ───────────────────────────────────────────────────── */
async function apiGet(path) {
  const r = await fetch(snSt.BASE + path, {
    signal: AbortSignal.timeout(6000),
  });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
async function apiPost(path, body) {
  const r = await fetch(snSt.BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || "HTTP " + r.status);
  }
  return r.json();
}
async function apiPut(path, body) {
  const r = await fetch(snSt.BASE + path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || "HTTP " + r.status);
  }
  return r.json();
}
async function apiDelete(path) {
  const r = await fetch(snSt.BASE + path, { method: "DELETE" });
  if (!r.ok && r.status !== 404) throw new Error("HTTP " + r.status);
}

/* ── Network list ──────────────────────────────────────────── */
async function refreshNetList() {
  setStatus("Loading networks…");
  try {
    const all = await apiGet("/configs?limit=500");
    // Only show records that are network graphs (identified by _type in data)
    const nets = all.filter((c) => c.data && c.data._type === "network");
    renderNetList(nets);
    setStatus(nets.length + " network(s) in database");
  } catch (e) {
    setStatus("Error loading networks: " + e.message, "err");
  }
}

function renderNetList(nets) {
  const ul = $q("#netList");
  if (!ul) return;
  ul.innerHTML = "";
  if (nets.length === 0) {
    ul.innerHTML =
      '<li style="padding:10px;color:#555;font-size:12px">No networks yet.<br>Click + to create one.</li>';
    return;
  }
  for (const net of nets) {
    const li = document.createElement("li");
    li.className = "sn-net-item" + (net.id === _activeId ? " active" : "");
    li.innerHTML =
      "<mat-icon>device_hub</mat-icon>" +
      '<span class="sn-net-name" title="' +
      esc(net.name) +
      '">' +
      esc(net.name) +
      "</span>" +
      '<button class="sn-net-del" title="Delete"><mat-icon>close</mat-icon></button>';
    li.querySelector(".sn-net-name").onclick = () => loadNetwork(net);
    li.querySelector(".sn-net-del").onclick = (e) => {
      e.stopPropagation();
      deleteNetwork(net);
    };
    ul.appendChild(li);
  }
}

/* ── Load a network into the canvas ───────────────────────── */
function loadNetwork(cfg) {
  if (!_graph) return;
  _graph.configure(cfg.data);
  _activeId = cfg.id;
  _activeName = cfg.name;
  const label = $q("#activeLabel");
  if (label) {
    label.textContent = cfg.name;
    label.className = "sn-active-label loaded";
  }
  const saveBtn = $q("#saveBtn");
  if (saveBtn) saveBtn.disabled = false;
  // Show canvas, hide empty placeholder
  $q("#simCanvas").style.display = "block";
  $q("#canvasEmpty").style.display = "none";
  // Resize to fit container
  self.onResize();
  const nodes = (_graph._nodes || []).length;
  setStatus("Loaded '" + cfg.name + "' — " + nodes + " node(s)", "ok");
  // Refresh list to update active highlight
  refreshNetList();
}

/* ── Save current graph ────────────────────────────────────── */
async function saveGraph() {
  if (!_graph || !_activeId) return;
  const graphData = Object.assign(_graph.serialize(), { _type: "network" });
  setStatus("Saving '" + _activeName + "'…");
  try {
    await apiPut("/configs/" + _activeId, {
      data: graphData,
      description: "Simulation network graph",
    });
    setStatus(
      "Saved '" +
        _activeName +
        "' (" +
        (_graph._nodes || []).length +
        " nodes)",
      "ok",
    );
  } catch (e) {
    setStatus("Save failed: " + e.message, "err");
  }
}

/* ── Create a new network ─────────────────────────────────── */
function closeNewNetDialog() {
  $q("#newNetModal").style.display = "none";
}

function showNewNetError(msg) {
  const el = $q("#newNetError");
  if (!el) return;
  el.textContent = msg;
  el.style.display = msg ? "block" : "none";
}
function openNewNetDialog() {
  $q("#newNetName").value = "";
  $q("#newNetDesc").value = "";
  showNewNetError("");
  $q("#newNetModal").style.display = "flex";
  setTimeout(() => $q("#newNetName").focus(), 50);
}
async function createNetwork() {
  const name = ($q("#newNetName").value || "").trim();
  const desc = ($q("#newNetDesc").value || "").trim();
  if (!name) {
    $q("#newNetName").focus();
    return;
  }
  showNewNetError("");
  setStatus("Creating '" + name + "'…");
  try {
    const emptyGraph = {
      _type: "network",
      nodes: [],
      links: [],
      groups: [],
      config: {},
      extra: {},
      version: 0.4,
    };
    const created = await apiPost("/configs", {
      name,
      description: desc || "Simulation network graph",
      data: emptyGraph,
    });
    closeNewNetDialog();
    setStatus("Created '" + name + "'", "ok");
    await refreshNetList();
    loadNetwork(created);
  } catch (e) {
    const msg =
      e.message.includes("409") ||
      e.message.toLowerCase().includes("already exists")
        ? "Name '" + name + "' already exists — choose another"
        : "Create failed: " + e.message;
    showNewNetError(msg);
    setStatus(msg, "err");
    $q("#newNetName").focus();
    $q("#newNetName").select();
  }
}

/* ── Delete a network ─────────────────────────────────────── */
async function deleteNetwork(cfg) {
  if (!confirm("Delete network '" + cfg.name + "'? This cannot be undone."))
    return;
  try {
    await apiDelete("/configs/" + cfg.id);
    if (cfg.id === _activeId) {
      _activeId = null;
      _activeName = null;
      _graph && _graph.clear();
      $q("#simCanvas").style.display = "none";
      $q("#canvasEmpty").style.display = "flex";
      const label = $q("#activeLabel");
      if (label) {
        label.textContent = "— no network loaded —";
        label.className = "sn-active-label";
      }
      const saveBtn = $q("#saveBtn");
      if (saveBtn) saveBtn.disabled = true;
    }
    setStatus("Deleted '" + cfg.name + "'");
    await refreshNetList();
  } catch (e) {
    setStatus("Delete failed: " + e.message, "err");
  }
}

/* ── Clear canvas ─────────────────────────────────────────── */
function clearGraph() {
  if (!_graph) return;
  _graph.clear();
  setStatus("Canvas cleared — remember to Save to persist");
}

/* ── Spawn node ────────────────────────────────────────────── */
function spawnNode(type) {
  if (!_graph || !_activeId) {
    setStatus("Load or create a network first", "err");
    return;
  }
  const node = LiteGraph.createNode(type);
  const ds = _lgCanvas.ds || _lgCanvas;
  const offset = ds.offset || [0, 0];
  const scale = ds.scale || 1;
  const cx = (_lgCanvas.canvas.width / 2 - offset[0]) / scale;
  const cy = (_lgCanvas.canvas.height / 2 - offset[1]) / scale;
  node.pos = [
    cx + (Math.random() - 0.5) * 120,
    cy + (Math.random() - 0.5) * 80,
  ];
  _graph.add(node);
  setStatus("Added " + node.title + " — click Save to persist");
}

/* ── Node type registrations ───────────────────────────────── */
function registerSimNodes() {
  function wp(node, key, val) {
    node.properties[key] = val;
  }

  function SourceNode() {
    this.addOutput("out", "flow");
    this.properties = {
      name: "source",
      inter_arrival_time_mean: 10.0,
      distribution: "exponential",
      active: true,
    };
    this.addWidget("string", "name", this.properties.name, (v) =>
      wp(this, "name", v),
    );
    this.addWidget(
      "number",
      "iat_mean",
      this.properties.inter_arrival_time_mean,
      (v) => wp(this, "inter_arrival_time_mean", v),
      { min: 0.1, max: 3600, step: 0.5, precision: 2 },
    );
    this.addWidget(
      "combo",
      "dist",
      this.properties.distribution,
      (v) => wp(this, "distribution", v),
      { values: ["exponential", "uniform", "deterministic"] },
    );
    this.addWidget("toggle", "active", this.properties.active, (v) =>
      wp(this, "active", v),
    );
    this.size = [210, 110];
    this.color = "#1b5e20";
    this.bgcolor = "#0a2e0f";
  }
  SourceNode.title = "⬤ Source";
  LiteGraph.registerNodeType("simulation/source", SourceNode);

  function QueueNode() {
    this.addInput("in", "flow");
    this.addOutput("out", "flow");
    this.properties = {
      name: "queue",
      capacity: 0,
      discipline: "FIFO",
      active: true,
    };
    this.addWidget("string", "name", this.properties.name, (v) =>
      wp(this, "name", v),
    );
    this.addWidget(
      "number",
      "capacity",
      this.properties.capacity,
      (v) => wp(this, "capacity", Math.round(v)),
      { min: 0, max: 10000, step: 1 },
    );
    this.addWidget(
      "combo",
      "discipline",
      this.properties.discipline,
      (v) => wp(this, "discipline", v),
      { values: ["FIFO", "LIFO", "PRIORITY"] },
    );
    this.addWidget("toggle", "active", this.properties.active, (v) =>
      wp(this, "active", v),
    );
    this.size = [210, 110];
    this.color = "#0d47a1";
    this.bgcolor = "#062060";
  }
  QueueNode.title = "▭ Queue";
  LiteGraph.registerNodeType("simulation/queue", QueueNode);

  function ProcessorNode() {
    this.addInput("in", "flow");
    this.addOutput("out", "flow");
    this.properties = {
      name: "processor",
      cycle_time: 5.0,
      capacity: 1,
      active: true,
    };
    this.addWidget("string", "name", this.properties.name, (v) =>
      wp(this, "name", v),
    );
    this.addWidget(
      "number",
      "cycle_time",
      this.properties.cycle_time,
      (v) => wp(this, "cycle_time", v),
      { min: 0.1, max: 3600, step: 0.5, precision: 2 },
    );
    this.addWidget(
      "number",
      "capacity",
      this.properties.capacity,
      (v) => wp(this, "capacity", Math.round(v)),
      { min: 1, max: 100, step: 1 },
    );
    this.addWidget("toggle", "active", this.properties.active, (v) =>
      wp(this, "active", v),
    );
    this.size = [210, 110];
    this.color = "#1a3f4f";
    this.bgcolor = "#0a2030";
  }
  ProcessorNode.title = "⚙ Processor";
  LiteGraph.registerNodeType("simulation/processor", ProcessorNode);

  function PdMNode() {
    this.addInput("in", "flow");
    this.addOutput("out", "flow");
    this.properties = {
      name: "pdm_proc",
      cycle_time: 1.0,
      capacity: 1,
      active: true,
      sensors: {
        pressure: { min: 10, max: 100, unit: "bar", distribution: "uniform" },
        vibration: { min: 0.1, max: 10, unit: "mm/s", distribution: "uniform" },
        volt: { min: 200, max: 240, unit: "V", distribution: "uniform" },
        rotation: { min: 100, max: 3000, unit: "RPM", distribution: "uniform" },
      },
    };
    this.addWidget("string", "name", this.properties.name, (v) =>
      wp(this, "name", v),
    );
    this.addWidget(
      "number",
      "cycle_time",
      this.properties.cycle_time,
      (v) => wp(this, "cycle_time", v),
      { min: 0.1, max: 600, step: 0.1, precision: 2 },
    );
    this.addWidget("toggle", "active", this.properties.active, (v) =>
      wp(this, "active", v),
    );
    this.addWidget(
      "number",
      "press.min",
      10,
      (v) => {
        this.properties.sensors.pressure.min = v;
      },
      { min: 0, max: 500, step: 1 },
    );
    this.addWidget(
      "number",
      "press.max",
      100,
      (v) => {
        this.properties.sensors.pressure.max = v;
      },
      { min: 0, max: 500, step: 1 },
    );
    this.addWidget(
      "number",
      "vib.min",
      0.1,
      (v) => {
        this.properties.sensors.vibration.min = v;
      },
      { min: 0, max: 100, step: 0.1 },
    );
    this.addWidget(
      "number",
      "vib.max",
      10,
      (v) => {
        this.properties.sensors.vibration.max = v;
      },
      { min: 0, max: 100, step: 0.1 },
    );
    this.size = [210, 200];
    this.color = "#4a1570";
    this.bgcolor = "#2a0a4f";
  }
  PdMNode.title = "📡 PdM Proc";
  LiteGraph.registerNodeType("simulation/pdm_processor", PdMNode);

  function SinkNode() {
    this.addInput("in", "flow");
    this.properties = { name: "sink", active: true };
    this.addWidget("string", "name", this.properties.name, (v) =>
      wp(this, "name", v),
    );
    this.addWidget("toggle", "active", this.properties.active, (v) =>
      wp(this, "active", v),
    );
    this.size = [200, 70];
    this.color = "#7f0000";
    this.bgcolor = "#4a0000";
  }
  SinkNode.title = "◼ Sink";
  LiteGraph.registerNodeType("simulation/sink", SinkNode);
}

/* ── Utils ─────────────────────────────────────────────────── */
function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/* ── Lifecycle ─────────────────────────────────────────────── */
self.onInit = function () {
  loadSettings();

  if (typeof LiteGraph === "undefined") {
    setStatus(
      "Litegraph.js not loaded — add CDN URL in widget Resources tab",
      "err",
    );
    return;
  }

  registerSimNodes();

  /* Boot graph + canvas (canvas hidden until a network is loaded) */
  const canvasEl = $q("#simCanvas");
  const wrap = $q("#canvasWrap");
  canvasEl.width = wrap.clientWidth || 800;
  canvasEl.height = wrap.clientHeight || 500;

  _graph = new LGraph();
  _lgCanvas = new LGraphCanvas(canvasEl, _graph);

  LiteGraph.NODE_DEFAULT_COLOR = "#1e1e1e";
  LiteGraph.NODE_DEFAULT_BGCOLOR = "#141414";
  LiteGraph.NODE_DEFAULT_TEXT_COLOR = "#e0e0e0";
  LiteGraph.LINK_COLOR = "#7c4dff";
  _lgCanvas.background_image = null;
  _lgCanvas.clear_background_color = "#141414";
  _lgCanvas.render_connection_arrows = true;
  _graph.start();

  /* Buttons */
  $q("#addSource").onclick = () => spawnNode("simulation/source");
  $q("#addQueue").onclick = () => spawnNode("simulation/queue");
  $q("#addProc").onclick = () => spawnNode("simulation/processor");
  $q("#addPdm").onclick = () => spawnNode("simulation/pdm_processor");
  $q("#addSink").onclick = () => spawnNode("simulation/sink");
  $q("#saveBtn").onclick = saveGraph;
  $q("#clearBtn").onclick = clearGraph;
  $q("#newNetBtn").onclick = openNewNetDialog;
  $q("#refreshNetBtn").onclick = refreshNetList;
  $q("#newNetCancel").onclick = closeNewNetDialog;
  $q("#newNetOk").onclick = createNetwork;
  $q("#settingsBtn").onclick = openSettings;
  $q("#cfgCancel").onclick = closeSettings;
  $q("#cfgSave").onclick = saveSettings;

  /* Enter key in new-network dialog */
  $q("#newNetName").onkeydown = (e) => {
    if (e.key === "Enter") createNetwork();
  };

  checkHealth();
  refreshNetList();
  _healthTimer = setInterval(checkHealth, 15000);
};

self.onDestroy = function () {
  if (_healthTimer) clearInterval(_healthTimer);
  if (_graph) {
    _graph.stop();
    _graph = null;
  }
  _lgCanvas = null;
};

self.onResize = function () {
  if (!_lgCanvas) return;
  const wrap = $q("#canvasWrap");
  if (!wrap) return;
  const el = $q("#simCanvas");
  el.width = wrap.clientWidth;
  el.height = wrap.clientHeight;
  _lgCanvas.resize(el.width, el.height);
};
