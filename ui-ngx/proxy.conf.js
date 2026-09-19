// SPDX-FileCopyrightText: Copyright The Thingsboard Authors
// SPDX-License-Identifier: Apache-2.0
const forwardUrl = "http://localhost:8080";
const aiAgentUrl = "http://localhost:8300";
const wsForwardUrl = "ws://localhost:8080";
const modelWsForwardUrl = process.env.MODEL_WS_FORWARD_URL || "ws://localhost:8082";
const ruleNodeUiforwardUrl = forwardUrl;

const PROXY_CONFIG = {
  "/api/ai-agent": {
    target: aiAgentUrl,
    secure: false,
  },
  "/api/models/ws": {
    target: modelWsForwardUrl,
    ws: true,
    secure: false,
    pathRewrite: {
      "^/api/models/ws": "/models/ws",
    },
  },
  "/api": {
    target: forwardUrl,
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
  "/api/ws": {
    target: wsForwardUrl,
    ws: true,
    secure: false,
  },
};

module.exports = PROXY_CONFIG;
