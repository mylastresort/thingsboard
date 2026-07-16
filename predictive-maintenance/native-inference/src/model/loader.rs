use anyhow::{Context, Result};
use ort::session::Session;
use ort::session::builder::SessionBuilder;
use serde::Deserialize;
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::Path;
use tracing::{debug, info};

#[derive(Debug, Clone, Deserialize)]
pub struct ModelMetadata {
    pub model_name: String,
    pub model_type: String,
    pub format: String,
    pub onnx_path: String,
    pub input_shape: Vec<Option<i64>>,
    pub input_dtype: String,
    pub input_names: Vec<String>,
    pub n_features: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ScalerMetadata {
    pub r#type: String,
    pub mean: Option<Vec<f64>>,
    pub scale: Option<Vec<f64>>,
    pub var: Option<Vec<f64>>,
    pub n_features_in: Option<usize>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LabelEncoderMetadata {
    pub classes: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct AnomalyConfig {
    pub feature_columns: Vec<String>,
    pub sensors: Vec<String>,
    pub error_keys: Vec<String>,
    pub component_keys: Vec<String>,
    pub prediction_horizons: Vec<u32>,
    pub algorithm: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ForecastConfig {
    pub algorithm: String,
    pub lookback_window: usize,
    pub forecast_horizon: usize,
    pub sensors: Vec<String>,
}

pub struct LoadedModel {
    pub session: RefCell<Session>,
    pub metadata: ModelMetadata,
}

pub struct AnomalyModelSet {
    pub binary_models: HashMap<u32, LoadedModel>,
    pub multiclass_models: HashMap<u32, LoadedModel>,
    pub label_encoder: LabelEncoderMetadata,
    pub config: AnomalyConfig,
}

pub struct ForecastModelSet {
    pub lstm_models: HashMap<String, LoadedModel>,
    pub scalers: HashMap<String, ScalerMetadata>,
    pub config: ForecastConfig,
}

fn load_json<T: for<'de> Deserialize<'de>>(path: &Path) -> Result<T> {
    let content = std::fs::read_to_string(path)
        .with_context(|| format!("Failed to read {:?}", path))?;
    Ok(serde_json::from_str(&content)?)
}

pub fn load_anomaly_models(model_dir: &Path) -> Result<AnomalyModelSet> {
    info!("Loading anomaly models from {:?}", model_dir);

    let config: AnomalyConfig = load_json(&model_dir.join("config.json"))?;

    let encoder_path = model_dir.join("label_encoder_meta.json");
    let label_encoder: LabelEncoderMetadata = if encoder_path.exists() {
        load_json(&encoder_path)?
    } else {
        LabelEncoderMetadata { classes: vec![] }
    };

    let mut binary_models = HashMap::new();
    let mut multiclass_models = HashMap::new();

    for &horizon in &config.prediction_horizons {
        let binary_meta_path = model_dir.join(format!("hour_{}_binary_meta.json", horizon));
        if binary_meta_path.exists() {
            let meta: ModelMetadata = load_json(&binary_meta_path)?;
            let onnx_path = model_dir.join(format!("hour_{}_binary.onnx", horizon));
            if onnx_path.exists() {
                let session = SessionBuilder::new()?.commit_from_file(&onnx_path)?;
                binary_models.insert(horizon, LoadedModel { session: RefCell::new(session), metadata: meta });
                debug!("Loaded binary model for horizon {}", horizon);
            }
        }

        let multi_meta_path = model_dir.join(format!("hour_{}_multiclass_meta.json", horizon));
        if multi_meta_path.exists() {
            let meta: ModelMetadata = load_json(&multi_meta_path)?;
            let onnx_path = model_dir.join(format!("hour_{}_multiclass.onnx", horizon));
            if onnx_path.exists() {
                let session = SessionBuilder::new()?.commit_from_file(&onnx_path)?;
                multiclass_models.insert(horizon, LoadedModel { session: RefCell::new(session), metadata: meta });
                debug!("Loaded multiclass model for horizon {}", horizon);
            }
        }
    }

    info!(
        "Loaded {} binary + {} multiclass anomaly models",
        binary_models.len(),
        multiclass_models.len()
    );

    Ok(AnomalyModelSet {
        binary_models,
        multiclass_models,
        label_encoder,
        config,
    })
}

pub fn load_forecast_models(model_dir: &Path) -> Result<ForecastModelSet> {
    info!("Loading forecast models from {:?}", model_dir);

    let config: ForecastConfig = load_json(&model_dir.join("config.json"))?;

    let mut lstm_models = HashMap::new();
    let mut scalers = HashMap::new();

    for sensor in &config.sensors {
        let meta_path = model_dir.join(format!("lstm_model_{}_meta.json", sensor));
        let xgb_meta_path = model_dir.join(format!("xgboost_forecast_{}_meta.json", sensor));

        let actual_meta_path = if meta_path.exists() {
            &meta_path
        } else if xgb_meta_path.exists() {
            &xgb_meta_path
        } else {
            continue;
        };

        let meta: ModelMetadata = load_json(actual_meta_path)?;
        let onnx_path = std::path::PathBuf::from(&meta.onnx_path);
        if onnx_path.exists() {
            let session = SessionBuilder::new()?.commit_from_file(&onnx_path)?;
            lstm_models.insert(sensor.clone(), LoadedModel { session: RefCell::new(session), metadata: meta });
            debug!("Loaded forecast model for sensor {}", sensor);
        }

        let scaler_path = model_dir.join(format!("scaler_{}_meta.json", sensor));
        if scaler_path.exists() {
            let scaler: ScalerMetadata = load_json(&scaler_path)?;
            scalers.insert(sensor.clone(), scaler);
        }
    }

    info!(
        "Loaded {} forecast models with {} scalers",
        lstm_models.len(),
        scalers.len()
    );

    Ok(ForecastModelSet {
        lstm_models,
        scalers,
        config,
    })
}
