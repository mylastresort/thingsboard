/* ============================================================
   FlexSim Simulations List — ThingsBoard static widget
   
   NAVIGATION: Row click → updateState(detailStateId, {
     entityId: { entityType:'DEVICE', id:'modelName::simName' },
     entityName: 'simName'
   })
   
   SETTINGS:
     serverBaseUrl   – e.g. http://localhost:8000
     apiToken        – e.g. jessica
     detailStateId   – TB state ID that hosts the Detail widget
                       (default: "simulation_detail")
   ============================================================ */

let _healthTimer = null;
let _editObs = null;

const state = {
  BASE: "",
  TOKEN: "jessica",
  DETAIL_STATE: "simulation",
  models: {},
  rows: [],
};

const LS_KEY = "flexsim_widget_settings";
const MEM_KEY = "_tbFlexSim";

/* ─ storage helpers ─ */
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
  // 1. in-memory (fastest, survives SPA nav)
  const mem = getMem();
  if (mem.serverBaseUrl) return mem;
  // 2. localStorage (survives page reload)
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
  // write to both layers
  const mem = getMem();
  Object.assign(mem, obj);
  const ls = getLS();
  if (ls) {
    try {
      ls.setItem(LS_KEY, JSON.stringify(obj));
    } catch (_) {}
  }
}

/* ── Settings ── */
function loadSettings() {
  const s = self.ctx.settings || {};
  const stored = storeRead();
  state.BASE = (
    stored.serverBaseUrl ||
    s.serverBaseUrl ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");
  state.TOKEN = stored.apiToken || s.apiToken || "jessica";
  state.DETAIL_STATE =
    stored.detailStateId || s.detailStateId || "simulation_detail";
}

function openSettings() {
  $q("#cfgUrl").value = state.BASE;
  $q("#cfgToken").value = state.TOKEN;
  $q("#cfgState").value = state.DETAIL_STATE;
  $q("#settingsModal").style.display = "flex";
}

function saveSettings() {
  const url = ($q("#cfgUrl").value || "").replace(/\/+$/, "");
  const token = ($q("#cfgToken").value || "").trim();
  const sid = ($q("#cfgState").value || "").trim();
  state.BASE = url;
  state.TOKEN = token;
  state.DETAIL_STATE = sid;
  storeWrite({ serverBaseUrl: url, apiToken: token, detailStateId: sid });
  // confirm
  const btn = $q("#cfgSave");
  if (btn) {
    btn.textContent = "Saved ✓";
    setTimeout(() => {
      btn.innerHTML = "Save &amp; Refresh";
    }, 1500);
  }
  setTimeout(() => {
    $q("#settingsModal").style.display = "none";
    setStatus("Settings saved ✓ — server: " + url);
    checkHealth();
    refresh();
  }, 400);
}

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

function setStatus(msg, isErr) {
  const el = $q("#sb");
  if (!el) return;
  el.textContent = msg;
  el.className = "fl-sb" + (isErr ? " err" : "");
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

async function apiFetch(method, path, params, body) {
  const opts = { method };
  if (body != null) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(apiUrl(path, params), opts);
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

/* ── Data loading ──────────────────────────────────────── */
async function refresh() {
  setStatus("Loading…");
  try {
    const md = await apiFetch("GET", "/flexsim/models", {});
    state.models = md.models || {};

    // Build rows from predefined configurations per model
    const names = Object.keys(state.models);
    state.rows = [];
    names.forEach((modelName) => {
      const info = state.models[modelName];
      const configs = Array.isArray(info.configurations)
        ? info.configurations
        : [];
      if (configs.length) {
        configs.forEach((configName) => {
          state.rows.push({
            modelName,
            simName: configName,
            runIds: [],
            hasData: false,
          });
        });
      } else {
        state.rows.push({
          modelName,
          simName: "—",
          runIds: [],
          hasData: false,
        });
      }
    });

    // Fetch run counts from the DB for each model in parallel (best-effort)
    const settled = await Promise.allSettled(
      names.map((n) =>
        apiFetch("GET", "/flexsim/optimization-results", { model_path: n }),
      ),
    );
    settled.forEach((r, i) => {
      const modelName = names[i];
      if (r.status !== "fulfilled") return;
      const sims = r.value.simulations || {};
      state.rows.forEach((row) => {
        if (row.modelName !== modelName || !sims[row.simName]) return;
        const sorted = [...sims[row.simName]].sort((a, b) => a - b);
        row.runIds = sorted;
        row.hasData = sorted.length > 0;
      });
    });

    renderTable();
    const ready = state.rows.filter((r) => r.hasData).length;
    setStatus(`${names.length} model(s) · ${ready} configuration(s) with data`);
  } catch (e) {
    setStatus("Error: " + e.message, true);
    renderTable();
  }
}

/* ── Table rendering ───────────────────────────────────── */
function renderTable() {
  const tbody = $q("#tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  if (!state.rows.length) {
    tbody.innerHTML = `
      <tr class="no-click">
        <td colspan="4" style="text-align:center;padding:20px;color:#aaa">
          No models found
        </td>
      </tr>`;
    return;
  }

  state.rows.forEach((row) => {
    const tr = document.createElement("tr");
    const canNav = row.simName !== "—";
    if (!canNav) tr.classList.add("no-click");

    tr.innerHTML = `
      <td class="fl-name" title="${esc(row.modelName)}">${esc(row.modelName)}</td>
      <td class="fl-sim"  title="${esc(row.simName)}">${esc(row.simName)}</td>
      <td>${row.runIds.length || "—"}</td>
      <td>
        <span class="fl-badge ${row.hasData ? "" : "no"}">${row.hasData ? "Ready" : "No data"}</span>
        ${canNav ? '<span class="fl-arrow">›</span>' : ""}
      </td>`;

    if (canNav) {
      tr.onclick = () => navigateToDetail(row);
    }
    tbody.appendChild(tr);
  });
}

/* ── Navigation ────────────────────────────────────────── */
function navigateToDetail(row) {
  // Pack model + sim into entityId.id as "modelName::simName".
  // entityName (= simName) is substituted into the TB state title via ${entityName}.
  // openState PUSHES onto the history stack so navigatePrevState() in the
  // detail widget correctly returns here (the list state) instead of jumping
  // all the way back to the root/parent dashboard state.
  try {
    self.ctx.stateController.openState(
      state.DETAIL_STATE,
      {
        entityId: {
          entityType: "DEVICE",
          id: `${row.modelName}::${row.simName}`,
        },
        entityName: row.simName,
        entityLabel: row.simName,
      },
      false, // don't open right layout
    );
  } catch (e) {
    setStatus("Navigation failed: " + e.message, true);
  }
}

/* ── Sync params ───────────────────────────────────────── */
async function syncParams() {
  const btn = $q("#syncBtn");
  if (btn) btn.disabled = true;
  setStatus("Syncing parameters…");
  try {
    // No model_path → server syncs all registered models
    await apiFetch("POST", "/flexsim/session/sync-parameters");
    setStatus("Parameters synced ✓");
  } catch (e) {
    setStatus("Sync failed: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ── Add configuration modal ──────────────────────────── */
function _populateCloneFrom(modelName) {
  const sel = $q("#mCloneFrom");
  const info = state.models[modelName] || {};
  const confs = Array.isArray(info.configurations) ? info.configurations : [];
  sel.innerHTML = confs.length
    ? confs.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")
    : '<option value="">No existing configurations</option>';
}

function openAddModal() {
  const sel = $q("#mModel");
  const keys = Object.keys(state.models);
  sel.innerHTML = keys.length
    ? keys.map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")
    : '<option value="">No models available</option>';
  sel.disabled = keys.length <= 1;
  _populateCloneFrom(sel.value);
  $q("#mConf").value = "";
  $q("#modal").style.display = "flex";
}

async function confirmAdd() {
  const modelName = $q("#mModel").value;
  const cloneFrom = $q("#mCloneFrom").value;
  const conf = $q("#mConf").value.trim();
  if (!modelName) {
    setStatus("No model selected", true);
    return;
  }
  if (!cloneFrom) {
    setStatus("No source configuration to clone from", true);
    return;
  }
  if (!conf) {
    setStatus("Configuration name is required", true);
    return;
  }
  $q("#modal").style.display = "none";
  setStatus(`Creating ${conf} (clone of ${cloneFrom}) in FlexSim…`);
  try {
    await apiFetch(
      "POST",
      "/flexsim/session/clone-job",
      {},
      { model_name: modelName, source_job: cloneFrom, new_job: conf },
    );
    setStatus(`Created: ${modelName} / ${conf}`);
    await refresh();
  } catch (e) {
    setStatus("Failed: " + e.message, true);
  }
}

/* ── Lifecycle ─────────────────────────────────────────── */
self.onInit = function () {
  injectDarkTbForm();
  loadSettings();

  $q("#refreshBtn").onclick = refresh;
  $q("#syncBtn").onclick = syncParams;
  $q("#settingsBtn").onclick = openSettings;
  $q("#addBtn").onclick = openAddModal;
  $q("#mModel").onchange = () => _populateCloneFrom($q("#mModel").value);
  $q("#mCancel").onclick = () => {
    $q("#modal").style.display = "none";
  };
  $q("#mOk").onclick = confirmAdd;
  $q("#cfgCancel").onclick = () => {
    $q("#settingsModal").style.display = "none";
  };
  $q("#cfgSave").onclick = saveSettings;

  checkHealth();
  _healthTimer = setInterval(checkHealth, 10000);
  refresh();

  // Toggle edit-mode (hide actions) and fullscreen (hide toolbar) classes
  function _applyModes() {
    const dash = document.querySelector(".tb-dashboard-page");
    const container = self.ctx.$container[0];
    const isEdit =
      (dash && dash.classList.contains("tb-edit-mode")) || !!self.ctx.isEdit;
    const isFs = !!container.closest(".tb-fullscreen");
    const root = container.querySelector(".fl-root");
    if (root) {
      root.classList.toggle("fl-editmode", isEdit);
      root.classList.toggle("fl-fullscreen", isFs);
    }
  }
  _editObs = new MutationObserver(_applyModes);
  const _dash = document.querySelector(".tb-dashboard-page");
  if (_dash) {
    _editObs.observe(_dash, { attributes: true, attributeFilter: ["class"] });
    // Also observe ancestors so we catch tb-fullscreen being added to a parent
    let _el = _dash;
    for (let i = 0; i < 5 && _el.parentElement; i++) {
      _el = _el.parentElement;
      _editObs.observe(_el, { attributes: true, attributeFilter: ["class"] });
    }
  }
  _applyModes();
};

self.onDestroy = function () {
  if (_healthTimer) {
    clearInterval(_healthTimer);
    _healthTimer = null;
  }
  if (_editObs) {
    _editObs.disconnect();
    _editObs = null;
  }
};

function injectDarkTbForm() {
  const id = "__fsw_tb_dark__";
  if (document.getElementById(id)) return;
  const el = document.createElement("style");
  el.id = id;
  el.textContent = `
    /* TB widget Appearance tab (MUI React form) – dark override */
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

self.typeParameters = function () {
  return { datasourcesOptional: true, dataKeysOptional: true };
};
