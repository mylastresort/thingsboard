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
const gatewayUrl = process.env.GATEWAY_URL || "http://proxy:80";
const wsGatewayUrl = gatewayUrl.replace(/^http/, "ws");

const PROXY_CONFIG = {
  // All API/static/auth traffic now goes through the HAProxy gateway,
  // which owns the routing to thingsboard vs model. The dev server
  // no longer needs to know about either backend directly.
  "/api": {
    target: gatewayUrl,
    secure: false,
  },
  "/api/ws": {
    target: wsGatewayUrl,
    ws: true,
    secure: false,
  },
  "/api/forecasts": {
    target: gatewayUrl,
    ws: true,
    secure: false,
  },
  "/static/rulenode": {
    target: gatewayUrl,
    secure: false,
  },
  "/static/widgets": {
    target: gatewayUrl,
    secure: false,
  },
  "/oauth2": {
    target: gatewayUrl,
    secure: false,
  },
  "/login/oauth2": {
    target: gatewayUrl,
    secure: false,
  },
};

module.exports = PROXY_CONFIG;