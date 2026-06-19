/* ============================================================
   FlexSim Simulation Detail — ThingsBoard static widget
   
   NAVIGATION IN:
     Reads stateController.getStateParams().entityId.id
     which the list widget encodes as  "modelName::simName"
   
   NAVIGATION BACK:
     Back button calls stateController.navigatePrevState()
   
   RESOURCES required:
     https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js
   
   SETTINGS:
     serverBaseUrl  – e.g. http://localhost:8000
     apiToken       – e.g. jessica
   ============================================================ */

let _chart = null;
let _healthTimer = null;
let _editObs = null;

const state = {
  BASE: "",
  TOKEN: "jessica",
  model: "",
  sim: "",
  results: null,
};

/* ── Helpers ───────────────────────────────────────────── */
function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

function setStatus(msg, level) {
  // level: 'err' | 'ok' | '' (default)
  const el = $q("#sb");
  if (!el) return;
  el.textContent = msg;
  el.className = "fd-sb" + (level ? " " + level : "");
}

function isDark() {
  return !!document
    .querySelector(".tb-dashboard-page")
    ?.classList.contains("dark");
}

/* ── Settings ── */
const LS_KEY = "flexsim_widget_settings";
const MEM_KEY = "_tbFlexSim";

function getTop() {
  try {
    return window.top || window;
  } catch (_) {
    return window;
  }
}
function getMem() {
  const top = getTop();
  if (!top[MEM_KEY]) top[MEM_KEY] = {};
  return top[MEM_KEY];
}
function getLS() {
  try {
    const ls = getTop().localStorage;
    ls.getItem("_");
    return ls;
  } catch (_) {}
  try {
    const ls = window.localStorage;
    ls.getItem("_");
    return ls;
  } catch (_) {}
  return null;
}
function storeRead() {
  const mem = getMem();
  if (mem.serverBaseUrl) return mem;
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
  const mem = getMem();
  Object.assign(mem, obj);
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
  state.BASE = (
    stored.serverBaseUrl ||
    s.serverBaseUrl ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");
  state.TOKEN = stored.apiToken || s.apiToken || "jessica";
}

function openSettings() {
  $q("#cfgUrl").value = state.BASE;
  $q("#cfgToken").value = state.TOKEN;
  $q("#settingsModal").style.display = "flex";
}

function saveSettings() {
  const url = ($q("#cfgUrl").value || "").replace(/\/+$/, "");
  const token = ($q("#cfgToken").value || "").trim();
  state.BASE = url;
  state.TOKEN = token;
  storeWrite({ serverBaseUrl: url, apiToken: token });
  const btn = $q("#cfgSave");
  if (btn) {
    btn.textContent = "Saved ✓";
    setTimeout(() => {
      btn.innerHTML = "Save &amp; Refresh";
    }, 1500);
  }
  setTimeout(() => {
    $q("#settingsModal").style.display = "none";
    setStatus("Settings saved – server: " + url);
    checkHealth();
    if (state.model && state.sim) loadResults(state.model, state.sim, null);
  }, 400);
}

/* ── Decode navigation state params ───────────────────── */
function getContext() {
  try {
    const p = self.ctx.stateController.getStateParams();
    const raw = p?.entityId?.id || "";
    const sep = raw.indexOf("::");
    if (sep < 0) return { modelName: raw, simName: "" };
    return {
      modelName: raw.substring(0, sep),
      simName: raw.substring(sep + 2),
    };
  } catch {
    return { modelName: "", simName: "" };
  }
}

/* ── API ───────────────────────────────────────────────── */
function apiUrl(path, params) {
  let url = state.BASE + path + "?token=" + encodeURIComponent(state.TOKEN);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v != null)
        url += "&" + encodeURIComponent(k) + "=" + encodeURIComponent(v);
    }
  }
  return url;
}

async function apiFetch(method, path, params) {
  const r = await fetch(apiUrl(path, params), { method });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const d = (await r.json()).detail;
      if (d != null) {
        detail = typeof d === "string" ? d : (d.message ?? JSON.stringify(d));
      }
    } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}

/* ── Health ────────────────────────────────────────────── */
async function checkHealth() {
  const text = $q("#hTxt");
  try {
    await apiFetch("GET", "/flexsim/session", {});
    if (text) text.textContent = "Online";
  } catch {
    if (text) text.textContent = "Offline";
  }
}

/* ── Load optimization results ─────────────────────────── */
async function loadResults(modelName, simName, runId) {
  showEmpty("Loading results…", false);
  setStatus("Loading results…");
  try {
    const params = { model_path: modelName, simulation_name: simName };
    if (runId != null) params.run_id = runId;
    const data = await apiFetch("GET", "/flexsim/optimization-results", params);
    state.results = data;

    // Populate objective selector
    const objSel = $q("#objSel");
    const prevObj = objSel.value;
    objSel.innerHTML = (data.objectives || [])
      .map(
        (o) =>
          `<option value="${o.name}">${o.name} ${o.maximize ? "(max)" : "(min)"}</option>`,
      )
      .join("");
    if (
      prevObj &&
      Array.from(objSel.options).some((o) => o.value === prevObj)
    ) {
      objSel.value = prevObj;
    }

    // Populate run selector
    const runSel = $q("#runSel");
    const avail = (data.available_runs || []).slice().reverse();
    runSel.innerHTML =
      '<option value="">Latest run</option>' +
      avail
        .map(
          (id) =>
            `<option value="${id}"${id === data.run_id ? " selected" : ""}>Run&nbsp;${id}</option>`,
        )
        .join("");

    // Render chart
    const currentObj = objSel.value || (data.objectives?.[0]?.name ?? "");
    renderChart(data, currentObj);
    showEmpty(null);

    // Status summary
    const bestIds = data.best_solution_ids || [];
    const bestIter = (data.iterations || []).find((it) =>
      bestIds.includes(it.solution_id),
    );
    const bestVal = bestIter?.[currentObj];
    setStatus(
      `Run ${data.run_id}  ·  ${(data.iterations || []).length} iterations` +
        (bestVal != null ? `  ·  Best: ${Number(bestVal).toFixed(6)}` : ""),
      "",
    );
  } catch (e) {
    showEmpty('No results yet. Press "Run Job" to start an optimization.');
    setStatus("Could not load results: " + e.message);
  }
}

/* ── Empty / chart panel toggle ────────────────────────── */
function showEmpty(msg, showIcon) {
  const empty = $q("#emptyPanel");
  const chart = $q("#chartEl");
  if (msg != null) {
    if (empty) {
      empty.style.display = "";
      const p = $q("#emptyMsg");
      if (p) p.textContent = msg;
      const ic = $q("#emptyIcon");
      if (ic) ic.style.display = showIcon === false ? "none" : "";
    }
    if (chart) chart.style.display = "none";
  } else {
    if (empty) empty.style.display = "none";
    if (chart) chart.style.display = "block";
    if (_chart) _chart.resize();
  }
}

/* ── Chart rendering (ECharts) ─────────────────────────── */
function renderChart(data, objName) {
  if (!_chart || !objName) return;

  const iters = data.iterations || [];
  const maximize = (data.objectives || []).find(
    (o) => o.name === objName,
  )?.maximize;
  const bestIds = data.best_solution_ids || [];

  // Lookup map: iteration number → full iteration object (for tooltip params)
  const iterMeta = {};
  iters.forEach((pt) => {
    iterMeta[pt.iteration] = pt;
  });

  const scatterPts = [];
  const bestPts = [];

  iters.forEach((pt) => {
    const v = pt[objName];
    if (v == null) return;
    // Keep data as plain [x, y] numbers — ECharts visualMap requires numeric dimensions.
    const point = [pt.iteration, v];
    if (bestIds.includes(pt.solution_id)) {
      bestPts.push(point);
    } else {
      scatterPts.push(point);
    }
  });

  const allVals = [...scatterPts, ...bestPts].map((p) => p[1]);
  const minV = allVals.length ? Math.min(...allVals) : 0;
  const maxV = allVals.length ? Math.max(...allVals) : 1;

  // Viridis-inspired color gradient
  // maximize=true → high values are "best" (yellow end)
  // maximize=false → low values are "best" (yellow end)
  const colorStops = maximize
    ? ["#440154", "#31688e", "#35b779", "#fde725"] // purple→blue→green→yellow (low→high)
    : ["#fde725", "#35b779", "#31688e", "#440154"]; // yellow→green→blue→purple (low→high)

  const dark = isDark();

  _chart.setOption(
    {
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 72, right: 32, top: 52, bottom: 56 },
      visualMap: {
        show: false,
        min: minV,
        max: maxV,
        inRange: { color: colorStops },
        seriesIndex: 0,
      },
      legend: {
        data: ["Feasible", "Best"],
        top: 8,
        right: 32,
        textStyle: { color: dark ? "#bbb" : "#555", fontSize: 12 },
        itemWidth: 14,
        itemHeight: 14,
      },
      tooltip: {
        trigger: "item",
        backgroundColor: dark ? "rgba(30,30,50,.92)" : "rgba(255,255,255,.95)",
        borderColor: dark ? "#555" : "#ddd",
        textStyle: { color: dark ? "#e0e0e0" : "#333", fontSize: 12 },
        formatter(p) {
          const v =
            typeof p.data[1] === "number" ? p.data[1].toFixed(6) : p.data[1];
          const tag =
            p.seriesIndex === 1 ? "★ Best solution" : "Feasible iteration";
          const params = iterMeta[p.data[0]]?.parameters ?? {};
          const paramKeys = Object.keys(params);
          let paramHtml = "";
          if (paramKeys.length) {
            paramHtml =
              '<hr style="margin:5px 0;border-color:rgba(128,128,128,.35)"/>' +
              '<div style="columns:2;column-gap:18px;font-size:11px">' +
              paramKeys
                .map((k) => {
                  const val = params[k];
                  const formatted =
                    typeof val === "number"
                      ? Number(val.toFixed(4)).toString()
                      : (val ?? "—");
                  return `<div style="white-space:nowrap"><span style="opacity:.65">${k}:</span> <b>${formatted}</b></div>`;
                })
                .join("") +
              "</div>";
          }
          return `<b>${tag}</b><br/>Iteration: <b>${p.data[0]}</b><br/>${objName}: <b>${v}</b>${paramHtml}`;
        },
      },
      xAxis: {
        name: "Iteration",
        nameLocation: "middle",
        nameGap: 38,
        min: 0,
        axisLine: { lineStyle: { color: dark ? "#444" : "#ccc" } },
        axisLabel: { color: dark ? "#aaa" : "#666", fontSize: 12 },
        splitLine: { show: false },
      },
      yAxis: {
        name: objName,
        nameLocation: "middle",
        nameGap: 64,
        axisLine: { lineStyle: { color: dark ? "#444" : "#ccc" } },
        axisLabel: { color: dark ? "#aaa" : "#666", fontSize: 12 },
        splitLine: {
          lineStyle: { color: dark ? "#2a2a3a" : "#efefef", type: "dashed" },
        },
      },
      series: [
        {
          name: "Feasible",
          type: "scatter",
          data: scatterPts,
          symbolSize: 10,
          emphasis: { scale: 1.6 },
        },
        {
          name: "Best",
          type: "scatter",
          data: bestPts,
          symbol: "diamond",
          symbolSize: 18,
          itemStyle: {
            color: "#ffd700",
            borderColor: "rgba(255,255,255,.85)",
            borderWidth: 1.5,
          },
          z: 10,
          emphasis: { scale: 1.5 },
        },
      ],
    },
    true,
  );
}

function exportCsv() {
  const data = state.results;
  if (!data || !(data.iterations || []).length) {
    setStatus("No results to export", "err");
    return;
  }
  const iters = data.iterations;
  const bestIds = new Set(data.best_solution_ids || []);
  const colSet = new Set();
  iters.forEach((r) => Object.keys(r).forEach((k) => colSet.add(k)));
  const cols = ["is_best", ...colSet];
  const escape = (v) => {
    const s = v == null ? "" : String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? '"' + s.replace(/"/g, '""') + '"'
      : s;
  };
  const lines = [cols.join(",")];
  iters.forEach((r) => {
    lines.push(
      cols
        .map((c) =>
          c === "is_best"
            ? bestIds.has(r.solution_id)
              ? "1"
              : "0"
            : escape(r[c]),
        )
        .join(","),
    );
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${state.model}_${state.sim}_run${data.run_id ?? ""}.csv`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 200);
  setStatus(`Exported ${iters.length} rows`, "ok");
}

/* ── Actions ───────────────────────────────────────────── */
async function runJob() {
  if (!state.model || !state.sim) return;
  const btn = $q("#runBtn");
  btn.disabled = true;
  btn.innerHTML = "<mat-icon>hourglass_empty</mat-icon><span>Running…</span>";
  setStatus(`Running ${state.sim}…`);
  try {
    const res = await apiFetch("POST", "/flexsim/session/run-simulation", {
      model_path: state.model,
      simulation_name: state.sim,
    });
    const rows = res.dataframe_shape?.rows ?? res.data?.length ?? "?";
    setStatus(`Job complete · ${rows} iteration(s) recorded`, "ok");
    // Reload to show fresh results
    await loadResults(state.model, state.sim, null);
  } catch (e) {
    const msg = e.message || "Unknown error";
    setStatus("Run failed: " + msg, "err");
    // Results (chart) are intentionally kept visible so previous data remains readable.
  } finally {
    btn.disabled = false;
    btn.innerHTML = "<mat-icon>play_arrow</mat-icon><span>Run Job</span>";
  }
}

async function openModel() {
  if (!state.model) return;
  setStatus(`Opening ${state.model} in FlexSim…`);
  try {
    await apiFetch("POST", "/flexsim/session/open", {
      model_path: state.model,
    });
    setStatus(`${state.model} opened`);
  } catch (e) {
    setStatus("Open failed: " + e.message, "err");
  }
}

async function syncParams() {
  if (!state.model) {
    setStatus("No model loaded — cannot sync parameters.", "err");
    return;
  }
  const btn = $q("#syncBtn");
  if (btn) btn.disabled = true;
  setStatus("Syncing parameters…");
  try {
    const params = { model_path: state.model };
    await apiFetch("POST", "/flexsim/session/sync-parameters", params);
    setStatus("Parameters synced ✓", "ok");
  } catch (e) {
    setStatus("Sync failed: " + e.message, "err");
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ── Lifecycle ─────────────────────────────────────────── */
self.onInit = function () {
  injectDarkTbForm();
  loadSettings();

  // Decode navigation context (modelName::simName from state params)
  const ctx = getContext();
  state.model = ctx.modelName;
  state.sim = ctx.simName;

  // Update breadcrumb labels inside widget
  const mLbl = $q("#modelLabel");
  const sLbl = $q("#simLabel");
  if (mLbl) mLbl.textContent = state.model || "Unknown";
  if (sLbl) sLbl.textContent = state.sim || "Unknown";

  // Update TB widget title bar to show simulation name
  if (state.sim) {
    try {
      self.ctx.widgetTitle = state.sim;
      self.ctx.detectChanges();
    } catch (_) {}
  }

  // Wire up controls
  $q("#backBtn").onclick = () => {
    try {
      // navigatePrevState(true) delegates to window.history.back() so the
      // browser steps back exactly one URL entry (list state) instead of
      // letting TB's internal stack collapse all the way to the root state.
      self.ctx.stateController.navigatePrevState(true);
    } catch {
      /* no prev state */
    }
  };
  $q("#openBtn").onclick = openModel;
  $q("#exportBtn").onclick = exportCsv;
  $q("#syncBtn").onclick = syncParams;
  $q("#runBtn").onclick = runJob;
  $q("#refreshBtn").onclick = () => loadResults(state.model, state.sim, null);
  $q("#settingsBtn").onclick = openSettings;
  $q("#cfgCancel").onclick = () => {
    $q("#settingsModal").style.display = "none";
  };
  $q("#cfgSave").onclick = saveSettings;
  $q("#objSel").onchange = () => {
    if (state.results) renderChart(state.results, $q("#objSel").value);
  };
  $q("#runSel").onchange = () => {
    const rid = $q("#runSel").value;
    loadResults(state.model, state.sim, rid || null);
  };

  // Health + data
  checkHealth();
  _healthTimer = setInterval(checkHealth, 10000);

  // Toggle edit-mode (hide actions) and fullscreen (hide toolbar) classes
  function _applyModes() {
    const dash = document.querySelector(".tb-dashboard-page");
    const container = self.ctx.$container[0];
    const isEdit =
      (dash && dash.classList.contains("tb-edit-mode")) || !!self.ctx.isEdit;
    const isFs = !!container.closest(".tb-fullscreen");
    const root = container.querySelector(".fd-root");
    if (root) {
      root.classList.toggle("fd-editmode", isEdit);
      root.classList.toggle("fd-fullscreen", isFs);
    }
  }
  _editObs = new MutationObserver(_applyModes);
  const _dash = document.querySelector(".tb-dashboard-page");
  if (_dash) {
    _editObs.observe(_dash, { attributes: true, attributeFilter: ["class"] });
    let _el = _dash;
    for (let i = 0; i < 5 && _el.parentElement; i++) {
      _el = _el.parentElement;
      _editObs.observe(_el, { attributes: true, attributeFilter: ["class"] });
    }
  }
  _applyModes();

  if (state.model && state.sim) {
    // Defer by one tick so the widget container has laid out and ECharts
    // gets real pixel dimensions on init (avoids 0×0 init on hidden element)
    setTimeout(() => {
      _chart = echarts.init($q("#chartEl"), isDark() ? "dark" : "light");
      loadResults(state.model, state.sim, null);
    }, 0);
  } else {
    _chart = echarts.init($q("#chartEl"), isDark() ? "dark" : "light");
    showEmpty("No simulation selected. Go back and choose one from the list.");
  }
};

self.onDestroy = function () {
  if (_healthTimer) {
    clearInterval(_healthTimer);
    _healthTimer = null;
  }
  if (_chart) {
    _chart.dispose();
    _chart = null;
  }
  if (_editObs) {
    _editObs.disconnect();
    _editObs = null;
  }
};

function injectDarkTbForm() {
  const id = "__fsw_tb_dark__";
  if (document.getElementById(id)) return; // already injected by widget1 or previous init
  const el = document.createElement("style");
  el.id = id;
  el.textContent = `
    .tb-json-form {
      background: transparent !important;
      color: rgba(255,255,255,0.87) !important;
    }
    .tb-json-form .SchemaForm,
    .tb-json-form > div { background: transparent !important; }
    .tb-json-form .MuiFormLabel-root {
      color: rgba(255,255,255,0.55) !important;
    }
    .tb-json-form .MuiInputBase-root {
      color: rgba(255,255,255,0.87) !important;
      background: transparent !important;
    }
    .tb-json-form .MuiInputBase-input {
      color: rgba(255,255,255,0.87) !important;
      caret-color: #90caf9 !important;
    }
    .tb-json-form .MuiInput-underline:before {
      border-bottom-color: rgba(255,255,255,0.3) !important;
    }
    .tb-json-form .MuiInput-underline:hover:not(.Mui-disabled):before {
      border-bottom-color: rgba(255,255,255,0.6) !important;
    }
    .tb-json-form .MuiInput-underline:after {
      border-bottom-color: #42a5f5 !important;
    }
  `;
  document.head.appendChild(el);
}

self.onResize = function () {
  if (_chart) _chart.resize();
};

self.typeParameters = function () {
  return { datasourcesOptional: true, dataKeysOptional: true };
};
