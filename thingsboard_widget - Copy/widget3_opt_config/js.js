/* ============================================================
   Optimization Config Builder — ThingsBoard widget (Latest Values)

   Workflow:
     1. Device list is sourced from the widget's configured datasource
        (entity type fixed to DEVICE; entity group set in widget config).
     2. For each selected device, fetches available telemetry keys.
     3. User picks key + time window → "Compute Bounds" fetches
        historical telemetry and auto-fills min / max.
     4. User adds performance measures manually (name, direction, agg).
     5. "Save Config" POSTs to the FastAPI backend
        (flexsim/optimization-configs).  The saved config can later
        be loaded by the Simulations List widget when creating an
        OptQuest job.

   Settings (ThingsBoard widget settings tab):
     serverBaseUrl  – FastAPI backend URL  (e.g. http://localhost:8000)
     apiToken       – FastAPI query token  (e.g. jessica)

   Datasource (widget config → Datasources tab):
     Add one datasource → Entity type: Device → entity filter: entity group.
     The widget reads ctx.datasources to build the device picker.
     No JWT or group-ID settings required — auth uses the TB session.
   ============================================================ */

/* ── State ──────────────────────────────────────────────────────────────── */
const state = {
  BASE: "http://localhost:8000",
  TOKEN: "jessica",

  devices: [], // [{ id, name }]
  parameters: [], // ParameterDef[]
  measures: [], // PerfMeasureDef[]
};

/* ── DOM helpers ────────────────────────────────────────────────────────── */
function $q(sel) {
  return self.ctx.$container[0].querySelector(sel);
}

function setStatus(msg, cls) {
  const el = $q("#statusBar");
  if (!el) return;
  el.textContent = msg;
  el.className = "oc-status" + (cls ? " " + cls : "");
}

/* ── Backend API helpers ────────────────────────────────────────────────── */
function backendUrl(path) {
  return (
    state.BASE +
    path +
    (path.includes("?") ? "&" : "?") +
    "token=" +
    encodeURIComponent(state.TOKEN)
  );
}

async function backendPost(path, body) {
  const res = await fetch(backendUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

/* ── ThingsBoard telemetry helpers ──────────────────────────────────────── */
// Runs inside ThingsBoard, so window.location.origin IS the TB server.
// JWT is read from TB's own localStorage key set on login.
async function tbGet(path) {
  let jwt = "";
  try {
    jwt = localStorage.getItem("jwt_token") || "";
  } catch (_) {}
  const res = await fetch(window.location.origin + path, {
    headers: {
      "X-Authorization": "Bearer " + jwt,
      "Content-Type": "application/json",
      accept: "application/json",
    },
  });
  if (!res.ok) throw new Error("TB " + res.status + " " + res.statusText);
  return res.json();
}

function populateDeviceSelect() {
  const sel = $q("#dlgDevice");
  const currentVal = sel.value; // preserve selection before rebuilding
  sel.innerHTML = '<option value="">— select —</option>';
  state.devices.forEach((d) => {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.name;
    sel.appendChild(opt);
  });
  // restore selection if the device is still in the list
  if (currentVal && state.devices.some((d) => d.id === currentVal)) {
    sel.value = currentVal;
  }
}

/* Fetch telemetry keys for the chosen device. */
async function loadTelemetryKeys(deviceId) {
  const keySel = $q("#dlgKey");
  const computeBtn = $q("#computeBtn");
  keySel.innerHTML = '<option value="">Loading…</option>';
  keySel.disabled = true;
  computeBtn.disabled = true;

  try {
    const keys = await tbGet(
      "/api/plugins/telemetry/DEVICE/" +
        encodeURIComponent(deviceId) +
        "/keys/timeseries",
    );
    keySel.innerHTML = '<option value="">— select —</option>';
    (keys || []).forEach((k) => {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = k;
      keySel.appendChild(opt);
    });
    keySel.disabled = false;
  } catch (err) {
    keySel.innerHTML = '<option value="">Error: ' + err.message + "</option>";
  }
}

/* Compute min/max from telemetry history. */
async function computeBounds() {
  const deviceId = $q("#dlgDevice").value;
  const key = $q("#dlgKey").value;
  const windowH = parseInt($q("#dlgWindow").value, 10);
  if (!deviceId || !key) return;

  const statusEl = $q("#computeStatus");
  statusEl.textContent = "Fetching…";
  statusEl.className = "oc-compute-status";
  $q("#computeBtn").disabled = true;

  try {
    const now = Date.now();
    const startTs = now - windowH * 3600 * 1000;

    // Use TB aggregate endpoints to get min and max in one combined call.
    const [minData, maxData] = await Promise.all([
      tbGet(
        "/api/plugins/telemetry/DEVICE/" +
          encodeURIComponent(deviceId) +
          "/values/timeseries?keys=" +
          encodeURIComponent(key) +
          "&startTs=" +
          startTs +
          "&endTs=" +
          now +
          "&limit=1&agg=MIN&interval=" +
          windowH * 3600 * 1000,
      ),
      tbGet(
        "/api/plugins/telemetry/DEVICE/" +
          encodeURIComponent(deviceId) +
          "/values/timeseries?keys=" +
          encodeURIComponent(key) +
          "&startTs=" +
          startTs +
          "&endTs=" +
          now +
          "&limit=1&agg=MAX&interval=" +
          windowH * 3600 * 1000,
      ),
    ]);

    const minArr = minData[key] || [];
    const maxArr = maxData[key] || [];

    if (!minArr.length || !maxArr.length) {
      throw new Error("No data in selected time window");
    }

    const minVal = parseFloat(minArr[0].value);
    const maxVal = parseFloat(maxArr[0].value);

    $q("#dlgMin").value = minVal;
    $q("#dlgMax").value = maxVal;

    // Auto-suggest label if blank
    const lblInput = $q("#dlgLabel");
    if (!lblInput.value) {
      const device = state.devices.find((d) => d.id === deviceId);
      const prefix = device ? device.name.replace(/\s+/g, "") + "_" : "";
      lblInput.value = prefix + key;
    }

    statusEl.textContent =
      "min=" + minVal.toFixed(4) + "  max=" + maxVal.toFixed(4);
    statusEl.className = "oc-compute-status ok";
  } catch (err) {
    statusEl.textContent = err.message;
    statusEl.className = "oc-compute-status err";
  } finally {
    $q("#computeBtn").disabled = false;
  }
}

/* ── Render parameters table ────────────────────────────────────────────── */
function renderParams() {
  const tbody = $q("#paramsTbody");
  const empty = $q("#paramsEmpty");

  // Remove all rows except the placeholder
  [...tbody.querySelectorAll("tr.oc-param-row")].forEach((r) => r.remove());

  if (state.parameters.length === 0) {
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";

  state.parameters.forEach((p, idx) => {
    const tr = document.createElement("tr");
    tr.className = "oc-param-row";
    tr.innerHTML =
      "<td><strong>" +
      esc(p.label) +
      "</strong></td>" +
      "<td>" +
      esc(p.device_name) +
      "</td>" +
      "<td><code>" +
      esc(p.telemetry_key) +
      "</code></td>" +
      "<td>" +
      p.time_window_hours +
      "h</td>" +
      "<td>" +
      p.min_val +
      "</td>" +
      "<td>" +
      p.max_val +
      "</td>" +
      "<td>" +
      (p.step_size != null ? p.step_size : "—") +
      "</td>" +
      '<td><button class="oc-del-btn" data-idx="' +
      idx +
      '" title="Remove">✕</button></td>';
    tbody.insertBefore(tr, empty);
  });

  tbody.querySelectorAll(".oc-del-btn").forEach((btn) => {
    btn.onclick = () => {
      state.parameters.splice(parseInt(btn.dataset.idx, 10), 1);
      renderParams();
    };
  });
}

/* ── Render performance measures table ──────────────────────────────────── */
function renderMeasures() {
  const tbody = $q("#measuresTbody");
  const empty = $q("#measuresEmpty");

  [...tbody.querySelectorAll("tr.oc-meas-row")].forEach((r) => r.remove());

  if (state.measures.length === 0) {
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";

  state.measures.forEach((m, idx) => {
    const dirBadge =
      m.direction === "minimize"
        ? '<span class="oc-badge oc-badge-min">Minimize</span>'
        : '<span class="oc-badge oc-badge-max">Maximize</span>';

    const tr = document.createElement("tr");
    tr.className = "oc-meas-row";
    tr.innerHTML =
      "<td><strong>" +
      esc(m.name) +
      "</strong></td>" +
      "<td>" +
      dirBadge +
      "</td>" +
      "<td>" +
      esc(m.aggregation) +
      "</td>" +
      '<td><button class="oc-del-btn" data-idx="' +
      idx +
      '" title="Remove">✕</button></td>';
    tbody.insertBefore(tr, empty);
  });

  tbody.querySelectorAll(".oc-del-btn").forEach((btn) => {
    btn.onclick = () => {
      state.measures.splice(parseInt(btn.dataset.idx, 10), 1);
      renderMeasures();
    };
  });
}

/* ── Dialog helpers ─────────────────────────────────────────────────────── */
function openParamDlg() {
  // Reset fields
  $q("#dlgMin").value = "";
  $q("#dlgMax").value = "";
  $q("#dlgStep").value = "";
  $q("#dlgLabel").value = "";
  $q("#dlgKey").innerHTML =
    '<option value="">— select a device first —</option>';
  $q("#dlgKey").disabled = true;
  $q("#computeBtn").disabled = true;
  $q("#computeStatus").textContent = "";
  $q("#computeStatus").className = "oc-compute-status";
  $q("#paramDlg").style.display = "flex";
}

function closeParamDlg() {
  $q("#paramDlg").style.display = "none";
}

function confirmParam() {
  const deviceId = $q("#dlgDevice").value;
  const key = $q("#dlgKey").value;
  const label = $q("#dlgLabel").value.trim();
  const minVal = parseFloat($q("#dlgMin").value);
  const maxVal = parseFloat($q("#dlgMax").value);
  const stepRaw = $q("#dlgStep").value;
  const stepVal = stepRaw !== "" ? parseFloat(stepRaw) : null;
  const windowH = parseInt($q("#dlgWindow").value, 10);

  if (!deviceId) {
    alert("Please select a device.");
    return;
  }
  if (!key) {
    alert("Please select a telemetry key.");
    return;
  }
  if (!label) {
    alert("Please enter a FlexSim parameter label.");
    return;
  }
  if (isNaN(minVal) || isNaN(maxVal)) {
    alert("Min and Max must be valid numbers.");
    return;
  }
  if (minVal >= maxVal) {
    alert("Min must be less than Max.");
    return;
  }

  const device = state.devices.find((d) => d.id === deviceId);
  state.parameters.push({
    label,
    device_id: deviceId,
    device_name: device ? device.name : deviceId,
    telemetry_key: key,
    time_window_hours: windowH,
    min_val: minVal,
    max_val: maxVal,
    step_size: stepVal,
  });

  renderParams();
  closeParamDlg();
}

function openMeasureDlg() {
  $q("#dlgMName").value = "";
  $q("#dlgMDir").value = "minimize";
  $q("#dlgMAgg").value = "Mean";
  $q("#measureDlg").style.display = "flex";
}

function closeMeasureDlg() {
  $q("#measureDlg").style.display = "none";
}

function confirmMeasure() {
  const name = $q("#dlgMName").value.trim();
  const dir = $q("#dlgMDir").value;
  const agg = $q("#dlgMAgg").value;
  if (!name) {
    alert("Please enter a performance measure name.");
    return;
  }
  state.measures.push({ name, direction: dir, aggregation: agg });
  renderMeasures();
  closeMeasureDlg();
}

/* ── Save config to backend ─────────────────────────────────────────────── */
async function saveConfig() {
  const name = ($q("#configName").value || "").trim();
  if (!name) {
    setStatus("Enter a config name first.", "err");
    return;
  }
  if (!state.parameters.length) {
    setStatus("Add at least one parameter.", "err");
    return;
  }
  if (!state.measures.length) {
    setStatus("Add at least one performance measure.", "err");
    return;
  }

  setStatus("Saving…");
  try {
    const result = await backendPost("/flexsim/optimization-configs", {
      name,
      parameters: state.parameters,
      performance_measures: state.measures,
    });
    setStatus(
      "Saved: " + result.name + " (id: " + result.id.slice(0, 8) + "…)",
      "ok",
    );
    // Optionally clear after save
    // clearAll();
  } catch (err) {
    setStatus("Save failed: " + err.message, "err");
  }
}

function clearAll() {
  $q("#configName").value = "";
  state.parameters = [];
  state.measures = [];
  renderParams();
  renderMeasures();
  setStatus("");
}

/* ── Utility ────────────────────────────────────────────────────────────── */
function esc(v) {
  return String(v ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Lifecycle ──────────────────────────────────────────────────────────── */
self.onInit = function () {
  const s = self.ctx.settings || {};
  state.BASE = (s.serverBaseUrl || "http://localhost:8000").replace(/\/+$/, "");
  state.TOKEN = s.apiToken || "jessica";

  // Bind static buttons
  $q("#refreshDevicesBtn").onclick = populateDeviceSelect;
  $q("#addParamBtn").onclick = openParamDlg;
  $q("#addMeasureBtn").onclick = openMeasureDlg;
  $q("#saveBtn").onclick = saveConfig;
  $q("#clearBtn").onclick = clearAll;

  // Parameter dialog
  $q("#paramCancel").onclick = closeParamDlg;
  $q("#paramOk").onclick = confirmParam;
  $q("#computeBtn").onclick = computeBounds;

  $q("#dlgDevice").onchange = function () {
    const deviceId = this.value;
    if (deviceId) {
      loadTelemetryKeys(deviceId);
      $q("#computeBtn").disabled = false;
    } else {
      $q("#dlgKey").innerHTML =
        '<option value="">— select a device first —</option>';
      $q("#dlgKey").disabled = true;
      $q("#computeBtn").disabled = true;
    }
  };

  $q("#dlgKey").onchange = function () {
    // Enable compute only when both device and key are set
    $q("#computeBtn").disabled = !(this.value && $q("#dlgDevice").value);
  };

  // Measure dialog
  $q("#measureCancel").onclick = closeMeasureDlg;
  $q("#measureOk").onclick = confirmMeasure;

  // Initial render (empty tables)
  renderParams();
  renderMeasures();

  // Device list arrives via self.onDataUpdated() once the datasource resolves.
  setStatus("Waiting for datasource\u2026");
};

self.onDestroy = function () {};

/* Declare widget as Latest Values so TB shows the Datasources config panel.
   Entity type is locked to DEVICE by the dashboard user's datasource filter.
   No data keys are required — we only need the entity list. */
self.typeParameters = function () {
  return {
    datasourcesOptional: false,
    maxDatasources: -1, // unlimited devices in the group
    dataKeysOptional: true, // no telemetry keys needed
    singleEntity: false,
  };
};

/* Called by TB each time the datasource subscription updates.
   Rebuilds the device picker from ctx.datasources (one entry per DEVICE).
   TB represents entityId as an object { entityType, id } — not a plain string. */
self.onDataUpdated = function () {
  const prev = state.devices.length;
  state.devices = (self.ctx.datasources || [])
    .filter(function (ds) {
      // entityType can be at the top level OR nested inside the entityId object
      const entityType =
        ds.entityType ||
        (ds.entityId && typeof ds.entityId === "object"
          ? ds.entityId.entityType
          : null);
      const entityId =
        ds.entityId && typeof ds.entityId === "object"
          ? ds.entityId.id
          : ds.entityId;
      return entityType === "DEVICE" && entityId;
    })
    .map(function (ds) {
      const entityId =
        ds.entityId && typeof ds.entityId === "object"
          ? ds.entityId.id
          : ds.entityId;
      return { id: entityId, name: ds.entityName || ds.name || entityId };
    });
  populateDeviceSelect();
  if (state.devices.length !== prev) {
    setStatus("Loaded " + state.devices.length + " device(s) from datasource.");
  }
};
