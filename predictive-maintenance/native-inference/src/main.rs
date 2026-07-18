mod config;
mod features;
mod kafka;
mod model;

use anyhow::Result;
use std::sync::Arc;
use std::sync::RwLock;
use tracing::{error, info, warn};

use crate::config::Config;
use crate::features::engineering::AnomalyFeatureEngineer;
use crate::kafka::consumer::{create_consumer, parse_command, poll_message, CommandType, ModelType};
use crate::kafka::producer::{create_producer, publish_prediction, publish_log, KafkaProducer};
use crate::model::loader::{load_anomaly_models, load_forecast_models, AnomalyModelSet, ForecastModelSet};
use crate::model::inference::{predict_anomaly, predict_forecast};

/// Shared application state.
struct AppState {
    anomaly_models: Option<AnomalyModelSet>,
    forecast_models: Option<ForecastModelSet>,
    config: Config,
}

fn load_models(config: &Config) -> Result<(Option<AnomalyModelSet>, Option<ForecastModelSet>)> {
    let anomaly_dir = config.models_path.join("anomaly");
    let forecast_dir = config.models_path.join("forecast");

    let anomaly_models = if anomaly_dir.exists() {
        match load_anomaly_models(&anomaly_dir) {
            Ok(models) => {
                info!("Loaded anomaly models from {:?}", anomaly_dir);
                Some(models)
            }
            Err(e) => {
                warn!("Failed to load anomaly models: {}", e);
                None
            }
        }
    } else {
        info!("No anomaly model directory at {:?}", anomaly_dir);
        None
    };

    let forecast_models = if forecast_dir.exists() {
        match load_forecast_models(&forecast_dir) {
            Ok(models) => {
                info!("Loaded forecast models from {:?}", forecast_dir);
                Some(models)
            }
            Err(e) => {
                warn!("Failed to load forecast models: {}", e);
                None
            }
        }
    } else {
        info!("No forecast model directory at {:?}", forecast_dir);
        None
    };

    Ok((anomaly_models, forecast_models))
}

fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    let config = Config::from_env();
    info!("Starting PdM Native Inference Engine");
    info!("Models path: {:?}", config.models_path);

    // Load models
    let (anomaly_models, forecast_models) = load_models(&config)?;

    let state = Arc::new(RwLock::new(AppState {
        anomaly_models,
        forecast_models,
        config: config.clone(),
    }));

    // Create Kafka producer
    let mut producer = create_producer(&config)?;

    // Create Kafka consumer
    let mut consumer = create_consumer(&config)?;

    info!("Starting command processing loop");

    // Main event loop
    loop {
        match poll_message(&mut consumer) {
            Some((_topic, payload)) => {
                match parse_command(&payload) {
                    Ok(cmd) => {
                        info!(
                            "Received command: {:?} for forecast_id={:?}",
                            cmd.command_type, cmd.forecast_id
                        );

                        if let Err(e) = handle_command(cmd, &state, &mut producer, &config) {
                            error!("Error handling command: {}", e);
                        }
                    }
                    Err(e) => {
                        warn!("Failed to parse command: {}", e);
                    }
                }
            }
            None => {
                // No message, sleep briefly
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
        }
    }
}

fn handle_command(
    cmd: kafka::consumer::PdmCommand,
    state: &Arc<RwLock<AppState>>,
    producer: &mut KafkaProducer,
    config: &Config,
) -> Result<()> {
    match cmd.command_type {
        CommandType::TRAIN => {
            info!("Training command received - Python training bridge handles this");
            publish_log(
                producer,
                &config.event_topic,
                &cmd.forecast_id,
                &cmd.forecast_id,
                "INFO",
                "native-inference",
                "TRAIN command received - delegating to Python training bridge",
            )?;
        }
        CommandType::INFER => {
            info!("Inference command received for {:?}", cmd.forecast_id);
            let state_guard = state.read().unwrap();

            match cmd.model_type.as_ref() {
                Some(ModelType::ANOMALY) | Some(ModelType::BOTH) => {
                    if let Some(ref anomaly_set) = state_guard.anomaly_models {
                        run_anomaly_inference(anomaly_set, &cmd, producer, config)?;
                    } else {
                        warn!("No anomaly models loaded");
                    }
                }
                Some(ModelType::FORECAST) => {
                    if let Some(ref forecast_set) = state_guard.forecast_models {
                        run_forecast_inference(forecast_set, &cmd, producer, config)?;
                    } else {
                        warn!("No forecast models loaded");
                    }
                }
                None => {
                    warn!("No model type specified in INFER command");
                }
            }
        }
        CommandType::STOP | CommandType::PAUSE | CommandType::UNPAUSE => {
            info!("Command {:?} received (handled by Python worker)", cmd.command_type);
        }
    }

    Ok(())
}

fn run_anomaly_inference(
    anomaly_set: &AnomalyModelSet,
    cmd: &kafka::consumer::PdmCommand,
    producer: &mut KafkaProducer,
    config: &Config,
) -> Result<()> {
    let engineer = AnomalyFeatureEngineer::new();

    // TODO: Fetch real telemetry from ThingsBoard API
    let features = vec![0.0f32; engineer.feature_count()];

    let predictions = predict_anomaly(anomaly_set, &features)?;

    for pred in &predictions {
        let result_json = serde_json::to_string(pred)?;
        publish_prediction(
            producer,
            &config.event_topic,
            &cmd.forecast_id,
            &cmd.forecast_id,
            "ANOMALY",
            None,
            &result_json,
        )?;

        if pred.failure_predicted && pred.general_failure_probability > 0.8 {
            if let Some(ref device_id) = cmd.device_id {
                let alarm_event = kafka::producer::PdmEvent {
                    event_type: kafka::producer::EventType::ALARM,
                    forecast_id: cmd.forecast_id.clone(),
                    model_id: cmd.forecast_id.clone(),
                    iteration: None,
                    timestamp: chrono::Utc::now().timestamp_millis(),
                    progress: None,
                    prediction: None,
                    alarm: Some(kafka::producer::AlarmPayload {
                        device_id: device_id.clone(),
                        severity: if pred.general_failure_probability > 0.9 {
                            "CRITICAL".into()
                        } else {
                            "MAJOR".into()
                        },
                        confidence_score: pred.general_failure_probability,
                        details_json: result_json.clone(),
                    }),
                    log: None,
                };
                kafka::producer::publish_event(producer, &config.event_topic, &alarm_event)?;
            }
        }
    }

    Ok(())
}

fn run_forecast_inference(
    forecast_set: &ForecastModelSet,
    cmd: &kafka::consumer::PdmCommand,
    producer: &mut KafkaProducer,
    config: &Config,
) -> Result<()> {
    let recent_values: Vec<f32> = vec![0.0; forecast_set.config.lookback_window];

    for (sensor, model) in &forecast_set.lstm_models {
        let predictions = predict_forecast(model, &recent_values, forecast_set.config.forecast_horizon)?;

        let result_json = serde_json::to_string(&serde_json::json!({
            "sensor": sensor,
            "predictions": predictions,
        }))?;

        publish_prediction(
            producer,
            &config.event_topic,
            &cmd.forecast_id,
            &cmd.forecast_id,
            "FORECAST",
            Some(sensor),
            &result_json,
        )?;
    }

    Ok(())
}
