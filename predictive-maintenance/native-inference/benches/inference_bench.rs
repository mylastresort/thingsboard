use std::time::Instant;
use ndarray::Array2;
use ort::{Session, SessionBuilder, inputs};

/// Benchmark Rust ONNX inference.
fn benchmark_onnx_inference(session: &Session, n_iterations: usize) -> (f64, f64) {
    // Generate synthetic features (26 features for anomaly detection)
    let input = Array2::from_shape_fn((1, 26), |(_, _)| rand::random::<f32>());

    // Warmup
    for _ in 0..10 {
        let _ = session.run(inputs!["input" => input.clone().into_dyn()]);
    }

    // Benchmark
    let start = Instant::now();
    for _ in 0..n_iterations {
        let _ = session.run(inputs!["input" => input.clone().into_dyn()]);
    }
    let elapsed = start.elapsed();

    let total_secs = elapsed.as_secs_f64();
    let latency_us = (total_secs / n_iterations as f64) * 1_000_000.0;
    let throughput = n_iterations as f64 / total_secs;

    (latency_us, throughput)
}

fn main() {
    println!("Rust ONNX Inference Benchmark");
    println!("=============================");

    let n_iterations = std::env::var("BENCH_ITERATIONS")
        .unwrap_or_else(|_| "10000".into())
        .parse()
        .unwrap_or(10000);

    let model_path = std::env::var("MODEL_PATH")
        .unwrap_or_else(|_| "models/anomaly/hour_1_binary.onnx".into());

    println!("Model: {}", model_path);
    println!("Iterations: {}", n_iterations);

    match SessionBuilder::new() {
        Ok(builder) => {
            match builder.commit_from_file(&model_path) {
                Ok(session) => {
                    println!("\nLoaded model: {}", model_path);

                    let (latency_us, throughput) = benchmark_onnx_inference(&session, n_iterations);

                    println!("\nResults:");
                    println!("  Avg latency: {:.2} us/op", latency_us);
                    println!("  Throughput: {:.0} ops/sec", throughput);
                    println!("  Total time: {:.4} sec", latency_us * n_iterations as f64 / 1_000_000.0);
                }
                Err(e) => {
                    eprintln!("Failed to load model: {}", e);
                    eprintln!("Using synthetic benchmark instead...");

                    // Synthetic benchmark: measure Rust overhead without real model
                    let input = Array2::from_shape_fn((1, 26), |(_, _)| rand::random::<f32>());

                    let start = Instant::now();
                    for _ in 0..n_iterations {
                        // Simulate the feature engineering + array creation overhead
                        let features: Vec<f32> = (0..26).map(|i| input[[0, i]]).collect();
                        let arr = Array2::from_shape_vec((1, 26), features).unwrap();
                        let _ = arr.sum();
                    }
                    let elapsed = start.elapsed();

                    let total_secs = elapsed.as_secs_f64();
                    let latency_us = (total_secs / n_iterations as f64) * 1_000_000.0;
                    let throughput = n_iterations as f64 / total_secs;

                    println!("\nSynthetic Results (array ops only):");
                    println!("  Avg latency: {:.2} us/op", latency_us);
                    println!("  Throughput: {:.0} ops/sec", throughput);
                }
            }
        }
        Err(e) => {
            eprintln!("Failed to create ort session builder: {}", e);
        }
    }
}
