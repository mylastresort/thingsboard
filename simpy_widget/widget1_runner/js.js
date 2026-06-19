/* ======================================================
   SimPy Line 2 — Simulation Runner
   ThingsBoard static widget

   RESOURCES required:
     https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js

   SETTINGS:
     serverBaseUrl  — e.g. http://localhost:9000
   ====================================================== */

let _cycleChart = null;
let _powerChart = null;
let _healthTimer = null;
let _runStart = null;

const st = {
  BASE: "http://localhost:9000",
  lastResult: null,
};

/* ── DOM helper ───────────────────────────────────────── */
function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

function isDark() {
  return !!document
    .querySelector(".tb-dashboard-page")
    ?.classList.contains("dark");
}

function applyTheme() {
  const root = $q(".sp-root");
  if (root) root.classList.toggle("dark", isDark());
}

/* ── Settings (persist via localStorage / window top) ── */
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
  const st_s = storeRead();
  st.BASE = (
    st_s.serverBaseUrl ||
    s.serverBaseUrl ||
    "http://localhost:9000"
  ).replace(/\/+$/, "");
}

function openSettings() {
  $q("#cfgUrl").value = st.BASE;
  $q("#settingsModal").style.display = "flex";
}
function closeSettings() {
  $q("#settingsModal").style.display = "none";
}
function saveSettings() {
  const url = ($q("#cfgUrl").value || "").replace(/\/+$/, "").trim();
  if (!url) return;
  st.BASE = url;
  storeWrite({ serverBaseUrl: url });
  closeSettings();
  setStatus("Settings saved — " + url, "ok");
  checkHealth();
}

/* ── Status bar ───────────────────────────────────────── */
function setStatus(msg, level) {
  const el = $q("#statusBar");
  if (!el) return;
  el.textContent = msg;
  el.className = "sp-status" + (level ? " " + level : "");
}

/* ── Health check ─────────────────────────────────────── */
async function checkHealth() {
  const dot = $q("#healthDot");
  const text = $q("#healthText");
  try {
    const r = await fetch(st.BASE + "/health", {
      signal: AbortSignal.timeout(4000),
    });
    const ok = r.ok;
    if (dot) {
      dot.className = "sp-dot " + (ok ? "ok" : "err");
    }
    if (text) {
      text.textContent = ok ? "API connected" : "API error " + r.status;
    }
  } catch (_) {
    if (dot) {
      dot.className = "sp-dot err";
    }
    if (text) {
      text.textContent = "Unreachable";
    }
  }
}

/* ── Run simulation ────────────────────────────────────── */
async function runSim() {
  const btn = $q("#runBtn");
  const simTime = parseFloat($q("#simTimeInput").value) || 28000;
  const seed = parseInt($q("#seedInput").value) || 42;

  btn.disabled = true;
  btn.innerHTML = "<mat-icon>hourglass_empty</mat-icon><span>Running…</span>";
  $q("#emptyState").style.display = "flex";
  $q("#emptyIcon").textContent = "hourglass_empty";
  $q("#emptyMsg").innerHTML =
    "Simulation running… <b>" + simTime.toLocaleString() + " s</b>";
  $q("#results").style.display = "none";
  $q("#configBadge").style.display = "none";
  setStatus("Sending POST /sim/run …");
  _runStart = Date.now();

  try {
    const r = await fetch(st.BASE + "/sim/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sim_time: simTime, random_seed: seed }),
    });

    if (!r.ok) {
      let detail = r.statusText;
      try {
        detail = (await r.json()).detail || detail;
      } catch (_) {}
      throw new Error("HTTP " + r.status + ": " + detail);
    }

    const data = await r.json();
    st.lastResult = data;

    const elapsed = ((Date.now() - _runStart) / 1000).toFixed(2);
    $q("#elapsed").textContent = "took " + elapsed + " s";
    $q("#elapsed").style.display = "";

    renderResults(data);
    setStatus(
      "Simulation complete — sim_time=" + simTime + " s, seed=" + seed,
      "ok",
    );
  } catch (e) {
    setStatus("Error: " + e.message, "err");
    $q("#emptyIcon").textContent = "error_outline";
    $q("#emptyMsg").textContent = "Error: " + e.message;
  } finally {
    btn.disabled = false;
    btn.innerHTML =
      "<mat-icon>play_arrow</mat-icon><span>Run Simulation</span>";
  }
}

/* ── Render results ────────────────────────────────────── */
function fmt(v, decimals) {
  if (v === undefined || v === null) return "—";
  const n = parseFloat(v);
  if (isNaN(n)) return "—";
  return decimals !== undefined ? n.toFixed(decimals) : n.toLocaleString();
}

function renderResults(data) {
  const sink2 = data.sink2 || {};
  const rs = data.final_resource_state || {};

  // KPI cards
  $q("#kpiThroughput").textContent = fmt(sink2.throughput_per_hour, 1);
  $q("#kpiArrivals").textContent = fmt(sink2.arrivals);
  $q("#kpiCycleAvg").textContent = fmt(sink2.cycle_time_avg, 1);
  $q("#kpiPowerAvg").textContent = fmt(sink2.power_avg, 0);

  // Source badge
  const badge = $q("#configBadge");
  badge.textContent = "config: " + (data.config_source || "defaults");
  badge.style.display = "";

  // Charts
  renderCycleChart(sink2);
  renderPowerChart(sink2);

  // Resource table
  const tbody = $q("#resourceTbody");
  tbody.innerHTML = "";
  for (const [name, s] of Object.entries(rs)) {
    let tag;
    if (s.queue > 0) {
      tag = '<span class="sp-tag sp-tag-queue">queued (' + s.queue + ")</span>";
    } else if (s.busy > 0) {
      tag = '<span class="sp-tag sp-tag-busy">busy</span>';
    } else {
      tag = '<span class="sp-tag sp-tag-idle">idle</span>';
    }
    tbody.innerHTML +=
      "<tr><td>" +
      name +
      "</td><td>" +
      s.busy +
      "</td><td>" +
      s.queue +
      "</td><td>" +
      tag +
      "</td></tr>";
  }

  // Show results, hide empty
  $q("#emptyState").style.display = "none";
  $q("#results").style.display = "flex";

  // Resize charts after layout
  setTimeout(() => {
    _cycleChart && _cycleChart.resize();
    _powerChart && _powerChart.resize();
  }, 50);
}

/* ── ECharts helpers ───────────────────────────────────── */
function chartTheme() {
  return isDark() ? "dark" : "light";
}

function makeBarOption(title, categories, values, color) {
  const theme = isDark();
  return {
    backgroundColor: "transparent",
    grid: { left: 60, right: 16, top: 8, bottom: 24, containLabel: false },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: function (params) {
        return (
          params[0].name +
          ": <b>" +
          parseFloat(params[0].value).toLocaleString(undefined, {
            maximumFractionDigits: 2,
          }) +
          "</b>"
        );
      },
    },
    xAxis: {
      type: "value",
      axisLine: { lineStyle: { color: theme ? "#555" : "#ccc" } },
      splitLine: { lineStyle: { color: theme ? "#333" : "#eee" } },
      axisLabel: { fontSize: 10, color: theme ? "#aaa" : "#757575" },
    },
    yAxis: {
      type: "category",
      data: categories,
      axisLabel: { fontSize: 11, color: theme ? "#ccc" : "#424242" },
      axisLine: { lineStyle: { color: theme ? "#555" : "#ccc" } },
    },
    series: [
      {
        type: "bar",
        data: values,
        barMaxWidth: 24,
        itemStyle: { color: color, borderRadius: [0, 3, 3, 0] },
        label: {
          show: true,
          position: "right",
          fontSize: 10,
          color: theme ? "#ccc" : "#424242",
          formatter: function (p) {
            return parseFloat(p.value).toLocaleString(undefined, {
              maximumFractionDigits: 1,
            });
          },
        },
      },
    ],
  };
}

function renderCycleChart(sink2) {
  const el = $q("#cycleChart");
  if (!el) return;

  if (!_cycleChart) {
    _cycleChart = echarts.init(el, chartTheme());
  }

  const cats = ["min", "avg", "max", "stdev"];
  const vals = [
    sink2.cycle_time_min ?? 0,
    sink2.cycle_time_avg ?? 0,
    sink2.cycle_time_max ?? 0,
    sink2.cycle_time_stdev ?? 0,
  ];

  _cycleChart.setOption(
    makeBarOption("Cycle Time", cats, vals, "#5c6bc0"),
    true,
  );
}

function renderPowerChart(sink2) {
  const el = $q("#powerChart");
  if (!el) return;

  if (!_powerChart) {
    _powerChart = echarts.init(el, chartTheme());
  }

  const cats = ["min", "avg", "max"];
  const vals = [
    sink2.power_min ?? 0,
    sink2.power_avg ?? 0,
    sink2.power_max ?? 0,
  ];

  _powerChart.setOption(makeBarOption("Power", cats, vals, "#039be5"), true);
}

/* ── Lifecycle ─────────────────────────────────────────── */
self.onInit = function () {
  loadSettings();
  applyTheme();

  $q("#runBtn").onclick = runSim;
  $q("#settingsBtn").onclick = openSettings;
  $q("#cfgCancel").onclick = closeSettings;
  $q("#cfgSave").onclick = saveSettings;

  checkHealth();
  _healthTimer = setInterval(checkHealth, 15000);
};

self.onDestroy = function () {
  if (_healthTimer) clearInterval(_healthTimer);
  if (_cycleChart) {
    _cycleChart.dispose();
    _cycleChart = null;
  }
  if (_powerChart) {
    _powerChart.dispose();
    _powerChart = null;
  }
};

self.onResize = function () {
  if (_cycleChart) _cycleChart.resize();
  if (_powerChart) _powerChart.resize();
};
