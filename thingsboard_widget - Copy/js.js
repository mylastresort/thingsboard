// ─────────────────────────────────────────────────────────────────────────────
//  FlexSim Simulation Manager – ThingsBoard Static Widget
//  Requires: ECharts 5  (add to Resources tab)
//    https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js
// ─────────────────────────────────────────────────────────────────────────────

let eChart = null;
let healthTimer = null;

const state = {
  BASE: "",
  TOKEN: "jessica",
  models: {}, // { modelName: filePath }
  rows: [], // [{ modelName, simName, runIds, lastRun }]
  sel: null, // selected row index
  results: null, // last /optimization-results response
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function isDark() {
  return !!document
    .querySelector(".tb-dashboard-page")
    ?.classList.contains("dark");
}

function apiUrl(path, params) {
  let url = state.BASE + path + "?token=" + encodeURIComponent(state.TOKEN);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v != null && v !== "") {
        url += "&" + encodeURIComponent(k) + "=" + encodeURIComponent(v);
      }
    }
  }
  return url;
}

async function api(method, path, params) {
  const res = await fetch(apiUrl(path, params), { method });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function setStatus(msg, isErr) {
  const el = $q("#statusBar");
  if (!el) return;
  el.textContent = msg;
  el.className = "fsm-status" + (isErr ? " err" : "");
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

self.onInit = function () {
  const s = self.ctx.settings || {};
  state.BASE = (s.serverBaseUrl || "http://localhost:8000").replace(/\/$/, "");
  state.TOKEN = s.apiToken || "jessica";

  // Init ECharts on the chart container
  eChart = echarts.init($q("#chartEl"), isDark() ? "dark" : "light");

  // Bind buttons
  $q("#refreshBtn").onclick = refresh;
  $q("#syncBtn").onclick = syncParams;
  $q("#addBtn").onclick = showModal;
  $q("#openBtn").onclick = openModel;
  $q("#closeBtn").onclick = closeModel;
  $q("#runBtn").onclick = runJob;
  $q("#dlgCancel").onclick = hideModal;
  $q("#dlgOk").onclick = confirmOpen;
  $q("#objSel").onchange = replotChart;
  $q("#runSel").onchange = function () {
    const row = state.rows[state.sel];
    if (row && row.simName !== "—") {
      loadResults(row.modelName, row.simName, $q("#runSel").value || null);
    }
  };

  // Health polling
  checkHealth();
  healthTimer = setInterval(checkHealth, 10000);

  // Initial data load
  refresh();
};

self.onDestroy = function () {
  if (healthTimer) clearInterval(healthTimer);
  if (eChart) {
    eChart.dispose();
    eChart = null;
  }
};

self.onResize = function () {
  if (eChart) eChart.resize();
};

self.typeParameters = function () {
  return { datasourcesOptional: true, dataKeysOptional: true };
};

// ── Health ─────────────────────────────────────────────────────────────────

async function checkHealth() {
  const dot = $q("#healthDot");
  const txt = $q("#healthText");
  if (dot) dot.className = "fsm-dot chk";
  try {
    await api("GET", "/flexsim/session", {});
    if (dot) dot.className = "fsm-dot on";
    if (txt) txt.textContent = "Online";
  } catch {
    if (dot) dot.className = "fsm-dot off";
    if (txt) txt.textContent = "Offline";
  }
}

// ── Data Loading ──────────────────────────────────────────────────────────────

async function refresh() {
  setStatus("Loading models…");
  try {
    const modData = await api("GET", "/flexsim/models", {});
    state.models = modData.models || {};

    // Populate dialog select
    const dlgSel = $q("#dlgSel");
    dlgSel.innerHTML = Object.keys(state.models)
      .map((n) => `<option value="${esc(n)}">${esc(n)}</option>`)
      .join("");

    // Fetch simulation lists per model in parallel
    state.rows = [];
    const modelNames = Object.keys(state.models);
    const results = await Promise.allSettled(
      modelNames.map((name) =>
        api("GET", "/flexsim/optimization-results", { model_path: name }),
      ),
    );

    results.forEach((r, i) => {
      const modelName = modelNames[i];
      if (r.status === "fulfilled") {
        const sims = r.value.simulations || {};
        const simEntries = Object.entries(sims);
        if (simEntries.length > 0) {
          simEntries.forEach(([simName, runIds]) => {
            const sorted = [...runIds].sort((a, b) => a - b);
            state.rows.push({
              modelName,
              simName,
              runIds: sorted,
              lastRun: Math.max(...sorted),
            });
          });
        } else if (
          r.value.available_runs &&
          r.value.available_runs.length > 0
        ) {
          const runs = r.value.available_runs;
          state.rows.push({
            modelName,
            simName: "(default)",
            runIds: runs,
            lastRun: Math.max(...runs),
          });
        } else {
          state.rows.push({
            modelName,
            simName: "—",
            runIds: [],
            lastRun: null,
          });
        }
      } else {
        // 404 / no DB yet — model exists but no runs
        state.rows.push({ modelName, simName: "—", runIds: [], lastRun: null });
      }
    });

    renderTable();
    setStatus(
      `${Object.keys(state.models).length} model(s) · ${state.rows.filter((r) => r.simName !== "—").length} simulation(s)`,
    );
  } catch (e) {
    setStatus("Failed to load: " + e.message, true);
    renderTable();
  }
}

function renderTable() {
  const tbody = $q("#tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (state.rows.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="4" style="text-align:center;padding:18px;color:#aaa">No models found</td></tr>';
    return;
  }

  state.rows.forEach((row, i) => {
    const hasData = row.lastRun != null;
    const tr = document.createElement("tr");
    if (state.sel === i) tr.className = "sel";
    tr.innerHTML = `
      <td style="font-weight:500">${esc(row.modelName)}</td>
      <td>${esc(row.simName)}</td>
      <td>${row.runIds.length || "—"}</td>
      <td><span class="fsm-badge ${hasData ? "fsm-badge-ok" : "fsm-badge-no"}">${hasData ? "Ready" : "None"}</span></td>
    `;
    tr.onclick = () => selectRow(i);
    tbody.appendChild(tr);
  });
}

function selectRow(idx) {
  state.sel = idx;
  const row = state.rows[idx];
  renderTable();

  const hasSim = row && row.simName !== "—";
  $q("#openBtn").disabled = !row;
  $q("#closeBtn").disabled = !row;
  $q("#runBtn").disabled = !hasSim;
  $q("#detailTitle").textContent = row
    ? `${row.modelName} / ${row.simName}`
    : "— Select a simulation —";

  if (hasSim) {
    loadResults(row.modelName, row.simName, null);
  } else {
    showEmptyState(true);
    setStatus("");
  }
}

// ── Results & Chart ───────────────────────────────────────────────────────────

async function loadResults(modelName, simName, runId) {
  showEmptyState(false, true);
  setStatus("Loading results…");
  try {
    const params = { model_path: modelName, simulation_name: simName };
    if (runId != null) params.run_id = runId;
    const data = await api("GET", "/flexsim/optimization-results", params);
    state.results = data;

    // Populate objective selector
    const objSel = $q("#objSel");
    const prevObj = objSel.value;
    objSel.innerHTML = (data.objectives || [])
      .map(
        (o) =>
          `<option value="${esc(o.name)}">${esc(o.name)} ${o.maximize ? "↑" : "↓"}</option>`,
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
    runSel.innerHTML =
      '<option value="">latest</option>' +
      [...(data.available_runs || [])]
        .reverse()
        .map(
          (id) =>
            `<option value="${id}"${id === data.run_id ? " selected" : ""}>Run ${id}</option>`,
        )
        .join("");
    runSel.style.display = (data.available_runs || []).length > 1 ? "" : "none";

    renderChart(data, objSel.value);
    showEmptyState(false, false);
    setStatus(
      `Run ${data.run_id} · ${(data.iterations || []).length} iterations`,
    );
  } catch (e) {
    showEmptyState(true);
    setStatus("No results yet — run the job first");
  }
}

function showEmptyState(visible, loading) {
  const em = $q("#emptyState");
  const ch = $q("#chartEl");
  if (visible || loading) {
    if (em) {
      em.style.display = "";
      em.innerHTML = loading
        ? "<mat-icon>hourglass_empty</mat-icon><p>Loading…</p>"
        : "<mat-icon>analytics</mat-icon><p>Select a simulation to view results</p>";
    }
    if (ch) ch.style.display = "none";
  } else {
    if (em) em.style.display = "none";
    if (ch) ch.style.display = "";
    if (eChart) eChart.resize();
  }
}

function replotChart() {
  if (state.results) renderChart(state.results, $q("#objSel").value);
}

function renderChart(data, objName) {
  if (!eChart || !objName) return;

  const iters = data.iterations || [];
  const maximize = (data.objectives || []).find(
    (o) => o.name === objName,
  )?.maximize;

  const feasible = [];
  const best = [];
  iters.forEach((pt) => {
    const v = pt[objName];
    if (v == null) return;
    (pt.best ? best : feasible).push([pt.iteration, v]);
  });

  // Gradient: viridis-like (purple=worst, yellow=best)
  const allVals = [...feasible, ...best].map((p) => p[1]);
  const minV = allVals.length ? Math.min(...allVals) : 0;
  const maxV = allVals.length ? Math.max(...allVals) : 1;

  // Color range direction based on minimize/maximize
  const colorRange = maximize
    ? ["#440154", "#31688e", "#35b779", "#fde725"] // low→bad purple, high→good yellow
    : ["#fde725", "#35b779", "#31688e", "#440154"]; // high→bad yellow, low→good purple

  const dark = isDark();

  eChart.setOption(
    {
      backgroundColor: "transparent",
      animation: false,
      grid: { left: 70, right: 22, top: 52, bottom: 52 },
      visualMap: {
        show: false,
        min: minV,
        max: maxV,
        inRange: { color: colorRange },
        seriesIndex: 0,
      },
      tooltip: {
        trigger: "item",
        formatter(p) {
          const v =
            typeof p.data[1] === "number" ? p.data[1].toFixed(4) : p.data[1];
          const label =
            p.seriesIndex === 1 ? "⭐ Best Iteration" : "Feasible Iteration";
          return `${label}<br/>Iteration: ${p.data[0]}<br/>${objName}: ${v}`;
        },
      },
      legend: {
        data: ["Feasible Iteration", "Best Iteration"],
        top: 8,
        textStyle: { color: dark ? "#bbb" : "#555", fontSize: 11 },
      },
      xAxis: {
        name: "Iteration",
        nameLocation: "middle",
        nameGap: 32,
        min: 0,
        axisLine: { lineStyle: { color: dark ? "#555" : "#ccc" } },
        axisLabel: { color: dark ? "#aaa" : "#666", fontSize: 11 },
        splitLine: { show: false },
      },
      yAxis: {
        name: objName,
        nameLocation: "middle",
        nameGap: 58,
        axisLine: { lineStyle: { color: dark ? "#555" : "#ccc" } },
        axisLabel: { color: dark ? "#aaa" : "#666", fontSize: 11 },
        splitLine: { lineStyle: { color: dark ? "#2a2a3e" : "#f0f0f0" } },
      },
      series: [
        {
          name: "Feasible Iteration",
          type: "scatter",
          data: feasible,
          symbolSize: 9,
        },
        {
          name: "Best Iteration",
          type: "scatter",
          data: best,
          symbol: "diamond",
          symbolSize: 14,
          itemStyle: { color: "#ffd700", borderColor: "#fff", borderWidth: 1 },
          z: 10,
        },
      ],
    },
    true,
  );
}

// ── Actions ───────────────────────────────────────────────────────────────────

async function syncParams() {
  const row = state.sel != null ? state.rows[state.sel] : null;
  if (!row) {
    setStatus("Select a model row before syncing parameters.", true);
    return;
  }
  const btn = $q("#syncBtn");
  btn.disabled = true;
  setStatus("Syncing parameters…");
  try {
    const params = { model_path: row.modelName };
    await api("POST", "/flexsim/session/sync-parameters", params);
    setStatus("Parameters synced ✓");
  } catch (e) {
    setStatus("Sync failed: " + e.message, true);
  } finally {
    btn.disabled = false;
  }
}

function showModal() {
  $q("#overlay").style.display = "flex";
}
function hideModal() {
  $q("#overlay").style.display = "none";
}

async function confirmOpen() {
  const name = $q("#dlgSel").value;
  if (!name) return;
  hideModal();
  setStatus(`Opening ${name}…`);
  try {
    await api("POST", "/flexsim/session/open", { model_path: name });
    setStatus(`${name} opened in FlexSim`);
    await refresh();
  } catch (e) {
    setStatus("Open failed: " + e.message, true);
  }
}

async function openModel() {
  const row = state.rows[state.sel];
  if (!row) return;
  setStatus(`Opening ${row.modelName}…`);
  try {
    await api("POST", "/flexsim/session/open", { model_path: row.modelName });
    setStatus(`${row.modelName} opened in FlexSim`);
  } catch (e) {
    setStatus("Open failed: " + e.message, true);
  }
}

async function closeModel() {
  const row = state.rows[state.sel];
  if (!row) return;
  setStatus(`Closing ${row.modelName}…`);
  try {
    await api("POST", "/flexsim/session/close", { model_path: row.modelName });
    setStatus(`${row.modelName} closed`);
    state.sel = null;
    $q("#openBtn").disabled = true;
    $q("#closeBtn").disabled = true;
    $q("#runBtn").disabled = true;
    $q("#detailTitle").textContent = "— Select a simulation —";
    showEmptyState(true);
    await refresh();
  } catch (e) {
    setStatus("Close failed: " + e.message, true);
  }
}

async function runJob() {
  const row = state.rows[state.sel];
  if (!row || row.simName === "—") return;

  const btn = $q("#runBtn");
  btn.disabled = true;
  btn.innerHTML = "<mat-icon>hourglass_empty</mat-icon> Running…";
  showEmptyState(false, true);
  setStatus(`Running ${row.simName}…`);

  try {
    const result = await api("POST", "/flexsim/session/run-simulation", {
      model_path: row.modelName,
      simulation_name: row.simName,
    });
    const iters = result.dataframe_shape?.rows ?? result.data?.length ?? "?";
    setStatus(`Job complete · ${iters} iterations recorded`);
    await refresh();
    await loadResults(row.modelName, row.simName, null);
  } catch (e) {
    setStatus("Job failed: " + e.message, true);
    showEmptyState(true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = "<mat-icon>play_arrow</mat-icon> Run Job";
  }
}
