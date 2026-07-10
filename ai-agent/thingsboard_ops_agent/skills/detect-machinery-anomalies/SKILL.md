---
name: detect-machinery-anomalies
description: >
  Use whenever the request asks to detect, flag, or explain "unusual",
  "abnormal", or "anomalous" vibration, temperature, pressure, or other
  telemetry changes in machinery/equipment — e.g. "detect unusual vibration
  in building 1", "is this pump running hot", "alert me on pressure spikes",
  or a fully-specified stats request like "compute mean/std and flag
  readings more than 2 std devs from the mean". This is a PHASED
  ELICITATION (Inversion) skill: ask everything still unanswered in ONE
  batched turn, then gate — do not call any telemetry or scope-resolution
  tool until Phase 1 is closed. Pair with find-devices-in-site for scope
  resolution and get-timeseries-data for the actual fetch once this
  skill's gate is passed.
tools: []
---

# Detect Machinery Anomalies

## Phase 0 — Extract before you ask

Before asking anything, read the user's own request and fill in every
Phase 1 item it already answers. A fully-specified request (method,
scope, time window, and action all stated or clearly implied in one
message) closes Phase 1 immediately with **zero questions asked** — go
straight to Phase 2/3 in the same turn. Only ask about items genuinely
left open. Never re-ask for something the user already told you.

## Phase 1 — Elicit (gate: nothing below runs until this phase closes)

Ask ALL of the still-unanswered items below **in a single turn** — never
one question per turn, never re-derive which ones are still open by
re-reasoning from scratch on each user reply. Track answered items as you
go; only re-ask what's missing.

1. **Method** — see "Method notes" below for the full list, including
   which needs are implied by each. If the user already spells out the
   exact computation (e.g. "compute the mean and standard deviation and
   flag anything past 2σ"), that is a fully answered Method — use it
   verbatim, even if it doesn't match one of the named presets below.
   Do not force it into the EWMA/baseline preset or ask for a baseline
   window it didn't request.
2. **Scope** — one device, a named device group, or a building/site (in
   which case resolution via find-devices-in-site happens in Phase 2, not
   as part of this question — just capture the site/group name here).
3. **Time window** — the period the _analysis itself_ covers (e.g. "last
   24h", "since last maintenance", "just check right now"). This is
   independent from any baseline window a statistical method needs (see
   below) — do not conflate the two or treat a mismatch between them as a
   blocker.
4. **Action on detection** — conversational report only, or create a
   standing alarm (severity + dedup behavior)?

### What closes Phase 1

- The user has answered every item above (directly or via Phase 0
  extraction), **or**
- The user says something equivalent to "proceed" / "just do it" / "use
  defaults" — in that case, immediately fill every _still-unanswered_ item
  with the default below, state in your next message which defaults you
  used, and move to Phase 2 in the same turn. "Proceed" is a closing signal,
  not a request for you to keep asking — never re-prompt after it.
- Do not treat an answered _time window_ as insufficient reason to close
  the gate on its own if the user has said "proceed" — one open question
  triggering a re-ask loop when a proceed signal was already given is the
  failure mode this skill exists to prevent.
- Do not stall in unstructured reasoning because a request doesn't map
  cleanly onto a named method preset. A fully-specified, if novel,
  statistical procedure is still an answered Method — treat "I don't have
  a bucket for this" as a reason to use the user's method as stated, never
  as a reason to keep deliberating instead of gating.

## Phase 2 — Resolve scope (only after Phase 1 closes)

If scope was a site/building name, load `find-devices-in-site` now to get
concrete device ids. If scope was already a device id/name, skip straight
to Phase 3.

## Phase 3 — Fetch & analyze

1. Load `get-timeseries-data` for the resolved device(s), keys implied by
   the request (vibration/temperature/pressure — resolve exact key names
   via `getTimeseriesKeys` per that skill's own rule, don't guess), and
   the time window from Phase 1.
2. **"Apply the method" always means delegating to `pandas_agent`.** Pass
   the fetched telemetry inline (via `run_pandas_code_tool`) along with a
   plain description of the exact computation from Phase 1 — e.g. "compute
   mean and standard deviation of these readings, then flag any hourly
   value more than 2 standard deviations from the mean." You never compute
   or reason through the statistics yourself, and you never state that you
   "cannot run pandas" or "cannot execute code" as a reason to skip this —
   that limitation is exactly why pandas_agent exists. If pandas_agent
   itself errors, report that error; do not silently fall back to manual
   reasoning over the raw numbers.

## Phase 4 — Act

Report findings conversationally. Only call `alarms_agent`/`saveAlarm` if
Phase 1's action-on-detection answer was "create an alarm" — never as an
implicit side effect of Phase 3 finding something.

## Method notes (what each needs, kept separate from the time-window question)

- **Fixed threshold**: needs a known safe range — ask if the user has one
  (spec sheet, ISO 10816/20816 class for vibration); never invent one.
- **Static window statistics**: mean/standard deviation computed directly
  over the analysis window itself (not a separate rolling baseline),
  flagging points beyond a stated σ multiple. This is the right bucket
  when the user states the computation directly (e.g. "mean, std dev,
  flag >2σ") without mentioning a baseline period — use their window as
  both the data and the reference, don't invent a second baseline window.
- **Statistical baseline (EWMA/z-score)**: needs its own _baseline_ window
  to compute the rolling mean/std from — this is separate from the
  Phase-1 _analysis_ time window, and only applies when the user actually
  wants a rolling/trailing reference distinct from the window being
  scanned. Default baseline: trailing 7 days, threshold 3σ, 2 consecutive
  breaching points required. If the user's analysis window is shorter
  than the baseline window (e.g. "check the last 24h" against a 7-day
  baseline), that's normal and expected — the baseline is the reference,
  the analysis window is what you're scanning for breaches. Not a
  conflict, don't flag it as one.
- **Rate-of-change**: needs a slope threshold or comparison point (e.g.
  "vs. 1 hour ago").
- **Cross-signal correlation**: needs to know which keys are relevant for
  the equipment type in scope.
- **Model-based residual**: only offer if the user mentions wanting to
  account for operating-condition variance (load, speed); don't suggest
  it unprompted, it's the heaviest option.

## Defaults (used only when the user signals "proceed"/"use your judgment")

- Method: EWMA/z-score, 7-day trailing baseline, 3σ threshold, 2
  consecutive breaches required.
- Scope: whatever devices were named or already resolved in this
  conversation — never silently expand to "all devices."
- Time window: latest value compared against the rolling baseline (i.e.
  "right now, in context of recent history"), not a one-off snapshot.
- Action on detection: conversational report, not an auto-created alarm.

## Hard rules

- Never invent a "safe" threshold number without a cited source (spec
  sheet, ISO standard, or the user's own stated baseline); say the
  threshold is unknown rather than fabricating one.
- Vibration RMS alone can't diagnose fault type (needs FFT/spectral
  analysis) — say so if the user wants root cause, not just detection.
- Never create or acknowledge alarms as a side effect of analysis — only
  on an explicit Phase 1 answer.
- Never re-derive "what's still missing" by re-reasoning over the whole
  conversation on every turn — track it forward from what's been answered.
- Never compute or reason through statistics yourself in place of calling
  pandas_agent, and never cite your own code-execution limits as a reason
  to skip, shortcut, or approximate the analysis.
