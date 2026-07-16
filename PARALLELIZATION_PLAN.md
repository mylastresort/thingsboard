# Parallelize PdM Training & Inference Per Sensor

## Current Architecture

**Two worker pools** (Docker-scaled):
- `pdm-forecast-worker` (5 instances) — LSTM per sensor
- `pdm-anomaly-worker` (5 instances) — RF per device (1 model, 14 hourly sub-models)

**Current bottleneck**: Both forecast training and inference iterate over sensors in a sequential `for` loop with zero parallelism across sensors.

---

## Parallelization Strategy

### 1. ForecastModel — Per-Sensor Training (Highest Impact)

**File**: `library/models/forecast_model.py` lines 163–227

**Current**: Sequential `for sensor_key, df in data.items()` — trains 1 LSTM at a time.

**Change**: Use `concurrent.futures.ThreadPoolExecutor` with configurable `max_workers` (default `os.cpu_count()` capped at 8).

```python
# forecast_model.py — train() method
from concurrent.futures import ThreadPoolExecutor, as_completed

def _train_single_sensor(self, sensor_key, df, progress_callback, sensor_index, total_sensors):
    """Isolated training for one sensor — runs in a thread."""
    sensor = prepare_sensor_data(df, sensor=sensor_key)
    train_data, test_data, scaler = scale_and_split_data(sensor, sensor_key, TRAIN_PERCENTAGE, self.lookback)
    train_x, train_y = create_rnn_dataset(train_data, self.lookback)
    train_x = np.reshape(train_x, (train_x.shape[0], 1, train_x.shape[1]))
    model = build_lstm_model(self.lookback, LSTM_UNITS, use_gpu=USE_GPU)
    model = train_lstm_model(model, train_x, train_y, EPOCHS, BATCH_SIZE, ...)
    return sensor_key, {"model": model, "scaler": scaler}
```

**Key considerations**:
- TensorFlow is thread-safe for independent model training on CPU. Each thread creates its own `Sequential` model.
- For GPU: `tf.device("/GPU:0")` — multiple TF threads share GPU; use `tf.config.experimental.set_memory_growth` (already enabled). Threads serialize on GPU anyway, so parallelism helps most on CPU-only or multi-GPU.
- Progress callbacks need thread-safe aggregation (use a `threading.Lock` around `_emit_training_progress`).

### 2. ForecastModel — Per-Sensor Inference

**File**: `library/models/forecast_model.py` lines 299–382

**Current**: Sequential `for sensor_key, model_dict in self.models.items()`.

**Change**: Same `ThreadPoolExecutor` pattern. Inference is cheap per sensor (single `model.predict()` call), so the overhead of thread pool is minimal.

```python
def _predict_single_sensor(self, sensor_key, model_dict, predict_for):
    """Isolated inference for one sensor."""
    # ... prepare data, scale, reshape, forecast_future()
    return sensor_key, result_dict
```

### 3. AnomalyPredictor — Hourly Model Training

**File**: `library/models/anomaly_predictor.py` lines 662–749

**Current**: Sequential `for hour in key_hours` (14 RF models).

**Change**: ThreadPoolExecutor. Each hour's (binary + multiclass) pair trains independently. RF already uses `n_jobs=-1`, so the benefit is moderate — best combined with reducing `n_jobs` per RF to avoid over-subscription.

```python
def _train_hourly_pair(hour, train, X_train, components, algorithm):
    """Train binary + multiclass RF for one hour."""
    # ... returns {f"hour_{hour}_multiclass": rf_mc, f"hour_{hour}_binary": rf_bin}
```

**Config**: `ANOMALY_MAX_WORKERS` env var (default 4). When training 14 models with 4 workers, reduces wall time ~3.5x.

### 4. activation.py — Train Forecast + Anomaly Concurrently

**File**: `src/pdm_worker/activation.py` lines 42–108

**Current**: Trains ForecastModel first, then AnomalyPredictor sequentially.

**Change**: When `model_type == "BOTH"`, use `ThreadPoolExecutor` or `threading.Thread` to train both concurrently. They share nothing except the `data_registry` (which is thread-safe — it only makes HTTP calls).

```python
# activation.py
from concurrent.futures import ThreadPoolExecutor

if target == "BOTH":
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_future = pool.submit(_train_forecast, ...)
        a_future = pool.submit(_train_anomaly, ...)
        f_future.result()  # propagate errors
        a_future.result()
    # start both inference jobs
    job_manager.start(forecast_model_id, ...)
    job_manager.start(anomaly_model_id, ...)
```

### 5. Job Manager — Concurrent Inference for Forecast + Anomaly

**File**: `src/model/job.py` lines 383–396

**Current**: Each model type gets its own thread. Within that thread, forecast iterates sensors sequentially.

**Change**: After parallelizing ForecastModel.predict(), no change needed at the job level. The thread already runs per-model-type.

---

## Configuration

| Env Var | Default | Controls |
|---|---|---|
| `PDM_FORECAST_TRAIN_WORKERS` | `4` | Thread pool size for forecast training |
| `PDM_FORECAST_PREDICT_WORKERS` | `4` | Thread pool size for forecast inference |
| `PDM_ANOMALY_TRAIN_WORKERS` | `4` | Thread pool size for anomaly training |
| `PDM_ANOMALY_MAX_WORKERS` | `4` | Docker scaling count (already exists) |

Add to `settings.py` and `config.py`:
```python
forecast_train_workers: int = int(os.getenv("PDM_FORECAST_TRAIN_WORKERS", "4"))
forecast_predict_workers: int = int(os.getenv("PDM_FORECAST_PREDICT_WORKERS", "4"))
anomaly_train_workers: int = int(os.getenv("PDM_ANOMALY_TRAIN_WORKERS", "4"))
```

---

## Files to Modify

| File | Change |
|---|---|
| `library/models/forecast_model.py` | Add `_train_single_sensor()`, `_predict_single_sensor()`, refactor `train()` and `predict()` to use `ThreadPoolExecutor` |
| `library/models/anomaly_predictor.py` | Add `_train_hourly_pair()`, refactor `create_and_train_hourly_models()` to use `ThreadPoolExecutor` |
| `src/pdm_worker/activation.py` | Train Forecast + Anomaly concurrently when `model_type == "BOTH"` |
| `src/pdm_worker/config.py` | Add `forecast_train_workers`, `forecast_predict_workers`, `anomaly_train_workers` |
| `src/settings.py` | Add corresponding env vars |
| `src/model/shared.py` | Thread-safe progress callback forwarding |

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| TF thread-safety on GPU | Each thread creates its own model; TF 2.x supports this. Set `TF_CPP_MIN_LOG_LEVEL=3` to suppress warnings. |
| Over-subscription (RF n_jobs=-1 + thread pool) | Set `n_jobs=2` when using thread pool for anomaly training, or `n_jobs=1` per RF when parallelizing across hours. |
| Progress reporting race conditions | Lock around `_emit_training_progress` and `update_training_progress`. |
| Memory pressure (multiple LSTM models in RAM) | Each sensor model is small (~few MB). Max 8 concurrent is safe on 8GB+ containers. |
| HTTP client thread-safety | `DataRegistry` uses `requests` which is thread-safe. Quarkus client uses `httpx` (async-capable, thread-safe). |

---

## Expected Speedup

| Workload | Current | Parallel (4 workers) | Parallel (8 workers) |
|---|---|---|---|
| Forecast train (10 sensors) | ~10x single | ~3x | ~2x |
| Forecast inference (10 sensors) | ~10x single | ~3x | ~2x |
| Anomaly train (14 models) | ~14x single | ~4x | ~2.5x |
| BOTH train (forecast + anomaly) | sequential | ~1.5-2x | ~1.5-2x |

Diminishing returns from TF GPU contention and Python GIL for I/O-bound parts. Real-world: **2–3x overall training speedup** with 4 workers.

---

## Implementation Order

1. `forecast_model.py` — parallelize `train()` per sensor (highest impact, most sensors)
2. `forecast_model.py` — parallelize `predict()` per sensor (same pattern)
3. `anomaly_predictor.py` — parallelize hourly model training
4. `activation.py` — concurrent forecast + anomaly training
5. Add config env vars
6. Test with `make pdm-forecast-worker` scaling and verify no regressions
