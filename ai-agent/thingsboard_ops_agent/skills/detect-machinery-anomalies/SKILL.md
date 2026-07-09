---
name: detect-machinery-anomalies
description: >
  Use whenever the request asks to detect, flag, or explain "unusual",
  "abnormal", or "anomalous" vibration, temperature, pressure, or other
  telemetry changes in machinery/equipment — e.g. "detect unusual vibration
  in building 1", "is this pump running hot", "alert me on pressure spikes".
  This is a PHASED ELICITATION (Inversion) skill: ask everything still
  unanswered in ONE batched turn, then gate — do not call any telemetry or
  scope-resolution tool until Phase 1 is closed. Pair with
  find-devices-in-site for scope resolution and get-timeseries-data for the
  actual fetch once this skill's gate is passed.
tools: []
---

# Detect Machinery Anomalies

## Phase 1 — Elicit (gate: nothing below runs until this phase closes)

On first load, ask ALL of the still-unanswered items below **in a single
turn** — never one question per turn, never re-derive which ones are still
open by re-reasoning from scratch on each user reply. Track answered items
as you go; only re-ask what's missing.

1. **Method** — fixed threshold / statistical baseline (EWMA-z-score) /
   rate-of-change / cross-signal correlation / model-based residual. See
   the method notes below for what each needs.
2. **Scope** — one device, a named device group, or a building/site (in
   which case resolution via find-devices-in-site happens in Phase 2, not
   as part of this question — just capture the site/group name here).
3. **Time window** — the period the *analysis itself* covers (e.g. "last
   24h", "since last maintenance", "just check right now"). This is
   independent from any baseline window a statistical method needs (see
   below) — do not conflate the two or treat a mismatch between them as a
   blocker.
4. **Action on detection** — conversational report only, or create a
   standing alarm (severity + dedup behavior)?

### What closes Phase 1

- The user has answered every item above, **or**
- The user says something equivalent to "proceed" / "just do it" / "use
  defaults" — in that case, immediately fill every *still-unanswered* item
  with the default below, state in your next message which defaults you
  used, and move to Phase 2 in the same turn. "Proceed" is a closing signal,
  not a request for you to keep asking — never re-prompt after it.
- Do not treat an answered *time window* as insufficient reason to close
  the gate on its own if the user has said "proceed" — one open question
  triggering a re-ask loop when a proceed signal was already given is the
  failure mode this skill exists to prevent.

## Phase 2 — Resolve scope (only after Phase 1 closes)

If scope was a site/building name, load `find-devices-in-site` now to get
concrete device ids. If scope was already a device id/name, skip straight
to Phase 3.

## Phase 3 — Fetch & analyze

Load `get-timeseries-data` for the resolved device(s), keys implied by the
request (vibration/temperature/pressure — resolve exact key names via
`getTimeseriesKeys` per that skill's own rule, don't guess), and the time
window from Phase 1. Apply the chosen method to what comes back.

## Phase 4 — Act

Report findings conversationally. Only call `alarms_agent`/`saveAlarm` if
Phase 1's action-on-detection answer was "create an alarm" — never as an
implicit side effect of Phase 3 finding something.

## Method notes (what each needs, kept separate from the time-window question)

- **Fixed threshold**: needs a known safe range — ask if the user has one
  (spec sheet, ISO 10816/20816 class for vibration); never invent one.
- **Statistical baseline (EWMA/z-score)**: needs its own *baseline* window
  to compute the rolling mean/std from — this is separate from the
  Phase-1 *analysis* time window. Default baseline: trailing 7 days,
  threshold 3σ, 2 consecutive breaching points required. If the user's
  analysis window is shorter than the baseline window (e.g. "check the
  last 24h" against a 7-day baseline), that's normal and expected — the
  baseline is the reference, the analysis window is what you're scanning
  for breaches. Not a conflict, don't flag it as one.
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