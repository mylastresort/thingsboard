---
name: get-timeseries-data
description: >
  Fetch time-series telemetry (latest snapshot or historical/aggregated range)
  for one target device, or for several devices at once. Use whenever the
  request names a device (or a set of devices already resolved to ids) and
  asks for telemetry values, a metric's current reading, its history, or an
  aggregate (avg/min/max) over a time window. Requires device ids already
  resolved — pair with find-devices-in-site first if the request only gives a
  building/site name.
tools:
  - getTimeseriesKeys
  - getLatestTimeseries
  - getTimeseries
  - getAttributesByScope
---

# Get Timeseries Data

Scoped to `telemetry_agent`'s tools only. This skill does not resolve device
ids from names/sites — if you only have a site or asset name, load
`find-devices-in-site` first to get device ids, then come back here.

## Decision tree

1. **"What's the current/latest value of X?"** (single device, single or few
   known keys) → `getLatestTimeseries(entityIdStr, entityType, keys?)`.
   Omit `keys` only if the caller wants *everything* currently reported —
   otherwise always pass explicit keys to avoid dumping unrelated series.

2. **"What keys does this device even report?"** (unknown telemetry schema,
   e.g. before asking for "pressure" on a device you haven't seen before) →
   `getTimeseriesKeys(entityIdStr, entityType)` first, then filter the
   result against what the user actually asked for before calling
   `getLatestTimeseries`/`getTimeseries`. Never guess a key name (e.g.
   `temperature` vs `temp` vs `bearingTemp`) — look it up.

3. **"Show me history / a trend / raw points over a range"** →
   `getTimeseries(entityIdStr, entityType, keys, startTs?, endTs?, agg=NONE,
   limit?, orderBy=DESC)`. Default `limit` to 100 unless the user asks for
   more; raw mode (`agg=NONE`) is the only mode where `limit` applies.

4. **"What's the average/min/max over period Y?"** →
   `getTimeseries(..., agg=AVG|MIN|MAX|SUM|COUNT, interval=<bucket_ms>)`.
   - Single aggregate over the whole window: set
     `interval = endTs - startTs + 1` (or `86400001` for "the whole day"
     trick) and `limit=1`.
   - Bucketed trend (e.g. hourly avg): set `interval` to the bucket size in
     ms (`3600000` = 1h) and omit `limit`.

5. **Device status alongside telemetry** (e.g. "is it online, and what's the
   latest reading") → telemetry_agent has no connectivity tool; pull
   `active`/`inactivityAlarmTime` via `getAttributesByScope(entityIdStr,
   entityType, scope='SERVER_SCOPE', keys='active,inactivityAlarmTime')`
   alongside the timeseries call. Do not infer online/offline from telemetry
   recency alone unless the user explicitly asks for that heuristic.

## Multi-device fetches

The telemetry_agent toolset has no batch/multi-entity call — `getLatestTimeseries`
and `getTimeseries` are single-entity only. For N devices:

- Resolve keys once per **distinct device type/profile** if devices share a
  schema (don't call `getTimeseriesKeys` N times for N identical sensors —
  call it once, reuse the key list for siblings of the same profile/type).
- Fan out one `getLatestTimeseries`/`getTimeseries` call per device id.
  Do this in parallel tool calls, not sequential turns, when the runtime
  supports concurrent tool calls.
- Assemble results into a single table/summary keyed by device name before
  answering — never surface raw per-call JSON to the user.
- If a device returns `[]` (empty), report it as "no telemetry yet" rather
  than silently omitting it or treating it as an error — empty is a valid,
  meaningful result (e.g. a provisioned-but-unfed sensor).

## Hard rules

- Never invent a telemetry key name, value, or timestamp. If unsure what a
  device reports, call `getTimeseriesKeys` — don't assume based on a
  similarly-named sibling device.
- Never silently drop devices that returned empty results from a multi-device
  summary — call out the gap explicitly.
- Prefer `agg`-based calls over pulling raw points and computing the
  aggregate yourself; the platform's aggregation is authoritative and cheaper.
- `useStrictDataTypes='true'` when the caller needs numeric types preserved
  (e.g. for downstream math/charting) rather than the default string
  conversion.
