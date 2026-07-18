"""
Benchmarks: Python vs Rust inference performance.

Run after training models to compare inference speeds.
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np


def benchmark_python_anomaly(model_dir: Path, n_iterations: int = 1000) -> Dict:
    """Benchmark Python anomaly inference."""
    import joblib

    model_files = list(model_dir.glob("hour_*_binary.joblib"))
    if not model_files:
        return {"error": "No models found"}

    # Load a model
    model = joblib.load(model_files[0])

    # Generate synthetic features (26 features)
    features = np.random.rand(1, 26).astype(np.float32)

    # Warmup
    for _ in range(10):
        model.predict(features)

    # Benchmark
    start = time.perf_counter()
    for _ in range(n_iterations):
        model.predict(features)
    elapsed = time.perf_counter() - start

    latency_us = (elapsed / n_iterations) * 1_000_000
    throughput = n_iterations / elapsed

    return {
        "engine": "Python (sklearn)",
        "model_type": "RandomForest",
        "iterations": n_iterations,
        "total_seconds": round(elapsed, 4),
        "avg_latency_us": round(latency_us, 2),
        "throughput_per_sec": round(throughput, 1),
    }


def benchmark_python_forecast(model_dir: Path, n_iterations: int = 1000) -> Dict:
    """Benchmark Python forecast inference."""
    import joblib

    scaler_files = list(model_dir.glob("scaler_*.pkl"))
    if not scaler_files:
        return {"error": "No scalers found"}

    scaler = joblib.load(scaler_files[0])

    # Generate synthetic data (lookback_window = 20)
    values = np.random.rand(20).astype(np.float32)

    # Warmup
    for _ in range(10):
        scaler.transform(values.reshape(-1, 1))

    # Benchmark
    start = time.perf_counter()
    for _ in range(n_iterations):
        scaler.transform(values.reshape(-1, 1))
    elapsed = time.perf_counter() - start

    latency_us = (elapsed / n_iterations) * 1_000_000
    throughput = n_iterations / elapsed

    return {
        "engine": "Python (sklearn)",
        "model_type": "StandardScaler",
        "iterations": n_iterations,
        "total_seconds": round(elapsed, 4),
        "avg_latency_us": round(latency_us, 2),
        "throughput_per_sec": round(throughput, 1),
    }


def benchmark_python_feature_engineering(n_iterations: int = 1000) -> Dict:
    """Benchmark Python feature engineering."""
    import pandas as pd

    # Generate synthetic telemetry
    n_points = 100
    sensors = ["volt", "rotate", "pressure", "vibration"]
    data = {s: np.random.rand(n_points) * 100 for s in sensors}
    df = pd.DataFrame(data)

    # Warmup
    for _ in range(10):
        for s in sensors:
            df[f"{s}mean_3h"] = df[s].rolling(3, min_periods=1).mean()
            df[f"{s}sd_3h"] = df[s].rolling(3, min_periods=1).std().fillna(0)
            df[f"{s}mean_24h"] = df[s].rolling(24, min_periods=1).mean()
            df[f"{s}sd_24h"] = df[s].rolling(24, min_periods=1).std().fillna(0)

    # Benchmark
    start = time.perf_counter()
    for _ in range(n_iterations):
        for s in sensors:
            df[f"{s}mean_3h"] = df[s].rolling(3, min_periods=1).mean()
            df[f"{s}sd_3h"] = df[s].rolling(3, min_periods=1).std().fillna(0)
            df[f"{s}mean_24h"] = df[s].rolling(24, min_periods=1).mean()
            df[f"{s}sd_24h"] = df[s].rolling(24, min_periods=1).std().fillna(0)
    elapsed = time.perf_counter() - start

    latency_us = (elapsed / n_iterations) * 1_000_000
    throughput = n_iterations / elapsed

    return {
        "engine": "Python (pandas)",
        "operation": "Feature Engineering (4 sensors)",
        "iterations": n_iterations,
        "total_seconds": round(elapsed, 4),
        "avg_latency_us": round(latency_us, 2),
        "throughput_per_sec": round(throughput, 1),
    }


def main():
    n_iters = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    model_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/models")

    results = {
        "benchmark_type": "python_vs_rust_inference",
        "iterations": n_iters,
        "python_results": {},
        "note": "Rust results should be added after running the Rust benchmark binary",
    }

    print(f"Running Python benchmarks ({n_iters} iterations)...")

    # Anomaly benchmark
    if model_dir.exists():
        result = benchmark_python_anomaly(model_dir, n_iters)
        results["python_results"]["anomaly"] = result
        print(f"  Anomaly: {result.get('avg_latency_us', 'N/A')} us/op, "
              f"{result.get('throughput_per_sec', 'N/A')} ops/sec")

    # Forecast benchmark
    if model_dir.exists():
        result = benchmark_python_forecast(model_dir, n_iters)
        results["python_results"]["forecast"] = result
        print(f"  Forecast: {result.get('avg_latency_us', 'N/A')} us/op, "
              f"{result.get('throughput_per_sec', 'N/A')} ops/sec")

    # Feature engineering benchmark
    result = benchmark_python_feature_engineering(n_iters)
    results["python_results"]["feature_engineering"] = result
    print(f"  Features: {result.get('avg_latency_us', 'N/A')} us/op, "
          f"{result.get('throughput_per_sec', 'N/A')} ops/sec")

    # Save results
    output_path = Path("benchmarks_python.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_path}")
    return results


if __name__ == "__main__":
    main()
