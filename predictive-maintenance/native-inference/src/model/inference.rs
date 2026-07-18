use anyhow::Result;
use ndarray::Array2;
use ort::inputs;
use ort::value::Tensor;
use serde::Serialize;
use std::collections::HashMap;

use super::loader::{AnomalyModelSet, LoadedModel};

#[derive(Debug, Clone, Serialize)]
pub struct AnomalyPrediction {
    pub failure_predicted: bool,
    pub general_failure_probability: f64,
    pub predicted_failing_component: String,
    pub class_probabilities: HashMap<String, f64>,
    pub horizon_hours: u32,
}

#[derive(Debug, Clone, Serialize)]
pub struct ForecastPrediction {
    pub sensor: String,
    pub predicted_value: f64,
    pub timestamp: String,
}

pub fn predict_anomaly(
    model_set: &AnomalyModelSet,
    features: &[f32],
) -> Result<Vec<AnomalyPrediction>> {
    let mut results = Vec::new();

    for (&horizon, binary_model) in &model_set.binary_models {
        let binary_output = run_classification(binary_model, features)?;
        let failure_prob = binary_output.1;

        if let Some(multi_model) = model_set.multiclass_models.get(&horizon) {
            let multi_output = run_classification(multi_model, features)?;
            let predicted_class_idx = multi_output.0;

            let predicted_component = model_set
                .label_encoder
                .classes
                .get(predicted_class_idx)
                .cloned()
                .unwrap_or_else(|| "unknown".into());

            let mut class_probs = HashMap::new();
            for (i, class_name) in model_set.label_encoder.classes.iter().enumerate() {
                if i < multi_output.2.len() {
                    class_probs.insert(class_name.clone(), multi_output.2[i]);
                }
            }

            results.push(AnomalyPrediction {
                failure_predicted: failure_prob > 0.5,
                general_failure_probability: failure_prob,
                predicted_failing_component: predicted_component,
                class_probabilities: class_probs,
                horizon_hours: horizon,
            });
        } else {
            results.push(AnomalyPrediction {
                failure_predicted: failure_prob > 0.5,
                general_failure_probability: failure_prob,
                predicted_failing_component: "unknown".into(),
                class_probabilities: HashMap::new(),
                horizon_hours: horizon,
            });
        }
    }

    Ok(results)
}

pub fn predict_forecast(
    model: &LoadedModel,
    recent_values: &[f32],
    n_steps: usize,
) -> Result<Vec<f32>> {
    let mut predictions = Vec::with_capacity(n_steps);
    let mut buffer = recent_values.to_vec();

    for _ in 0..n_steps {
        let start = buffer.len().saturating_sub(model.metadata.n_features);
        let input_slice = &buffer[start..];
        let output = run_regression(model, input_slice)?;
        predictions.push(output);
        buffer.push(output);
    }

    Ok(predictions)
}

fn run_classification(model: &LoadedModel, features: &[f32]) -> Result<(usize, f64, Vec<f64>)> {
    let input_array = Array2::from_shape_vec((1, features.len()), features.to_vec())?;
    let shape = input_array.shape().to_vec();
    let data = input_array.into_raw_vec();
    let tensor = Tensor::from_array((shape, data))?;

    let mut session = model.session.borrow_mut();
    let outputs = session.run(inputs![tensor])?;

    let output_value = &outputs[0];
    let (_output_shape, output_data) = output_value.try_extract_tensor::<f32>()?;
    let flat: Vec<f32> = output_data.to_vec();

    if flat.is_empty() {
        return Ok((0, 0.0, vec![]));
    }

    if flat.len() == 2 {
        let probs: Vec<f64> = flat.iter().map(|&p| p as f64).collect();
        let predicted = if probs[1] > probs[0] { 1 } else { 0 };
        return Ok((predicted, probs[1], probs));
    }

    let probs: Vec<f64> = flat.iter().map(|&p| p as f64).collect();
    let predicted = probs
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
        .map(|(i, _)| i)
        .unwrap_or(0);

    Ok((predicted, probs.get(1).copied().unwrap_or(0.0), probs))
}

fn run_regression(model: &LoadedModel, features: &[f32]) -> Result<f32> {
    let input_array = Array2::from_shape_vec((1, features.len()), features.to_vec())?;
    let shape = input_array.shape().to_vec();
    let data = input_array.into_raw_vec();
    let tensor = Tensor::from_array((shape, data))?;

    let mut session = model.session.borrow_mut();
    let outputs = session.run(inputs![tensor])?;

    let output_value = &outputs[0];
    let (_output_shape, output_data) = output_value.try_extract_tensor::<f32>()?;
    let flat: Vec<f32> = output_data.to_vec();

    Ok(flat.first().copied().unwrap_or(0.0))
}

pub fn scale_features(features: &[f32], mean: &[f64], scale: &[f64]) -> Vec<f32> {
    features
        .iter()
        .zip(mean.iter())
        .zip(scale.iter())
        .map(|((&x, &m), &s)| {
            if s != 0.0 {
                ((x as f64 - m) / s) as f32
            } else {
                x
            }
        })
        .collect()
}

pub fn inverse_scale(value: f32, mean: f64, scale: f64) -> f32 {
    if scale != 0.0 {
        (value as f64 * scale + mean) as f32
    } else {
        value
    }
}
