# PdM Native Inference Engine

High-performance Rust-based inference for ThingsBoard predictive maintenance.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Training Phase (Python)                    │
│                                                              │
│  training_bridge/                                            │
│  ├── AnomalyTrainer   → trains RF/XGB → exports ONNX        │
│  ├── ForecastTrainer  → trains LSTM   → exports ONNX        │
│  └── OnnxExporter     → sklearn/keras → .onnx files         │
│                                                              │
│  Output: {model_dir}/anomaly/*.onnx, forecast/*.onnx        │
└──────────────────────────┬──────────────────────────────────┘
                           │ ONNX models
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  Inference Phase (Rust)                       │
│                                                              │
│  native-inference/                                           │
│  ├── model/loader.rs      → loads ONNX via ort crate        │
│  ├── model/inference.rs   → runs predictions                │
│  ├── features/engineering.rs → Rust feature engineering     │
│  ├── kafka/consumer.rs    → consumes PDM commands           │
│  └── kafka/producer.rs    → publishes PDM events            │
│                                                              │
│  Input: Kafka pdm-commands (INFER)                           │
│  Output: Kafka pdm-events (PREDICTION, ALARM)                │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

1. **ONNX as the bridge**: Python trains models, exports to ONNX. Rust loads ONNX via the `ort` crate.
2. **Thin Python layer**: `training_bridge/` is the ONLY Python code that touches ML frameworks.
3. **Native inference**: Rust eliminates GIL, GC pauses, and framework overhead for 10-50x speedup.
4. **Feature engineering in Rust**: The 26-feature anomaly pipeline runs natively in Rust.

## Model Format

All models are exported to ONNX format:
- **Anomaly**: 14 ONNX files (7 horizons × 2 types: binary + multiclass)
- **Forecast**: 1 ONNX file per sensor (LSTM or XGBoost)
- **Scalers**: JSON metadata (mean, scale) for Rust to load
- **Label encoder**: JSON metadata for class names

## Build

```bash
# Build Rust binary
cd native-inference
cargo build --release

# Or build Docker image
docker build -f .Dockerfile.native -t pdm-native .
```

## Run

```bash
# Set environment
export MODELS_PATH=/app/models
export KAFKA_BROKERS=localhost:9092
export PDM_COMMAND_TOPIC=pdm-commands
export PDM_EVENT_TOPIC=pdm-events
export RUST_LOG=info

# Run the inference service
./target/release/pdm-native-inference
```

## Benchmarks

```bash
# Run all benchmarks
./run_benchmarks.sh 10000

# Or individually
python3 benchmarks.py 10000
cd native-inference && cargo run --release
```

## Expected Performance

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| RF Inference (1 sample) | ~500 us | ~10 us | 50x |
| XGB Inference (1 sample) | ~200 us | ~5 us | 40x |
| LSTM Inference (1 step) | ~2000 us | ~50 us | 40x |
| Feature Engineering | ~5000 us | ~100 us | 50x |
| StandardScaler | ~100 us | ~2 us | 50x |

## File Structure

```
predictive-maintenance/
├── training_bridge/          # Python: train + export to ONNX
│   ├── __init__.py
│   ├── onnx_exporter.py      # sklearn/keras → ONNX conversion
│   ├── anomaly_trainer.py    # Anomaly model training
│   ├── forecast_trainer.py   # Forecast model training
│   └── train_and_export.py   # Integration script
│
├── native-inference/         # Rust: load ONNX + run inference
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs           # Entry point + command handling
│   │   ├── config/mod.rs     # Configuration
│   │   ├── model/
│   │   │   ├── loader.rs     # ONNX model loading
│   │   │   └── inference.rs  # Prediction logic
│   │   ├── features/
│   │   │   └── engineering.rs # Feature engineering in Rust
│   │   └── kafka/
│   │       ├── consumer.rs   # Kafka command consumer
│   │       └── producer.rs   # Kafka event producer
│   └── benches/
│       └── inference_bench.rs
│
├── .Dockerfile.native        # Docker image with Rust + Python
├── benchmarks.py             # Python benchmark script
└── run_benchmarks.sh         # Combined benchmark runner
```
