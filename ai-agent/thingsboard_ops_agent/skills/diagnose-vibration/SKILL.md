---
name: diagnose-vibration
description: Diagnose vibration issues on rotating machinery. Use when the user wants FFT analysis, envelope spectrum, bearing fault detection, ISO 10816 severity assessment, or full automated vibration diagnosis.
---

# Diagnose Vibration

Goal: perform vibration signal analysis and rotating machinery fault detection
through the `vibration_agent` specialist.

## Steps

1. **List available sensors**: Call `vibration_agent` with
   `list_vibration_sensors(site_name, asset_id)` to see which vibration
   sensor fields are available for the asset.

2. **Load vibration data**: Call `get_vibration_data(site_name, asset_id,
   sensor_name, start, final)` to fetch time-series from CouchDB and load
   into the analysis store. This returns a `data_id` for subsequent analysis.

3. **Quick FFT**: For a fast frequency-domain overview, call
   `compute_fft_spectrum(data_id)` to get top-N peaks and spectral stats.

4. **Bearing analysis**: Call `compute_envelope_spectrum(data_id)` for
   envelope-based bearing fault detection. Optionally specify `band_low_hz`
   and `band_high_hz` to focus on a resonance band.

5. **Full diagnosis**: Call `diagnose_vibration(data_id, rpm=..., ...)` for
   the complete pipeline:
   - FFT + shaft-frequency feature extraction (requires RPM)
   - Envelope analysis for bearing faults (if bearing info provided)
   - Fault classification (unbalance, misalignment, looseness, bearing)
   - ISO 10816 severity assessment
   - Human-readable markdown report

   Bearing info can be supplied as:
   - Direct fault frequencies: `bpfo_hz`, `bpfi_hz`, `bsf_hz`, `ftf_hz`
   - Custom geometry: `bearing_n_balls`, `bearing_ball_dia_mm`, `bearing_pitch_dia_mm`
   - Database lookup: `bearing_designation` (e.g. '6205', 'NU206')

6. **Bearing frequencies**: Call `calculate_bearing_frequencies(rpm, n_balls,
   ball_diameter_mm, pitch_diameter_mm)` to compute BPFO/BPFI/BSF/FTF from
   geometry. Call `list_known_bearings()` to see the built-in database.

7. **ISO severity only**: Call `assess_vibration_severity(rms_velocity_mm_s,
   machine_group)` for standalone ISO 10816 classification. Machine groups:
   group1 (large/rigid), group2 (medium/rigid), group3 (large/flexible),
   group4 (small).

Always provide RPM when possible — without it, shaft-frequency analysis
(1x, 2x, etc.) is skipped and fault classification is limited.
