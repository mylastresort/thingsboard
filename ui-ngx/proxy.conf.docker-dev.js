/*
 * Copyright © 2016-2026 The Thingsboard Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
const forwardUrl = process.env.HOSTS || "http://thingsboard:8080";
const wsForwardUrl = forwardUrl.replace(/^http/, "ws");
const ruleNodeUiforwardUrl = forwardUrl;
const modelUrl = process.env.MODEL_URL || "http://model:8000";
const modelWsUrl = modelUrl.replace(/^http/, "ws");

const PROXY_CONFIG = {
  // ── Model container routes (bypass ThingsBoard) ──────────────────────────

  // /api/v1/* → model:8000  (model's native prefix: activate, ws, etc.)
  "/api/v1": {
    target: modelUrl,
    secure: false,
    ws: true,
  },

  // /api/models/* → model:8000/api/v1/models/*
  "/api/models": {
    target: modelUrl,
    secure: false,
    pathRewrite: { "^/api/models": "/api/v1/models" },
  },

  // /api/predictiveMaintenance/* → model:8000/api/v1/predictiveMaintenance/*
  "/api/predictiveMaintenance": {
    target: modelUrl,
    secure: false,
    pathRewrite: { "^/api/predictiveMaintenance": "/api/v1/predictiveMaintenance" },
  },

  // /api/forecasts* → model:8000/api/v1/forecast*
  // (TB used /forecasts plural, FastAPI uses /forecast singular)
  "/api/forecasts": {
    target: modelUrl,
    secure: false,
    pathRewrite: { "^/api/forecasts": "/api/v1/forecast" },
    ws: true,
  },

  // /api/devices-with-models → model:8000/api/v1/devices-with-models
  "/api/devices-with-models": {
    target: modelUrl,
    secure: false,
    pathRewrite: { "^/api/devices-with-models": "/api/v1/devices-with-models" },
  },

  // /api/notify-* → model:8000 (notification hooks called by ThingsBoard rule engine)
  "/api/notify": {
    target: modelUrl,
    secure: false,
  },

  // ── ThingsBoard routes (auth, devices, telemetry, dashboards, …) ─────────
  "/api": {
    target: forwardUrl,
    secure: false,
  },
  "/api/ws": {
    target: wsForwardUrl,
    ws: true,
    secure: false,
  },
  "/static/rulenode": {
    target: ruleNodeUiforwardUrl,
    secure: false,
  },
  "/static/widgets": {
    target: forwardUrl,
    secure: false,
  },
  "/oauth2": {
    target: forwardUrl,
    secure: false,
  },
  "/login/oauth2": {
    target: forwardUrl,
    secure: false,
  },
};

module.exports = PROXY_CONFIG;
