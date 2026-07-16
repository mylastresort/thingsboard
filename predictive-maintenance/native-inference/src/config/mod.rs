use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct Config {
    pub models_path: PathBuf,
    pub kafka_brokers: String,
    pub command_topic: String,
    pub event_topic: String,
    pub consumer_group: String,
    pub inference_interval_secs: u64,
    pub anomaly_interval_secs: u64,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            models_path: PathBuf::from(
                std::env::var("MODELS_PATH").unwrap_or_else(|_| "/app/models".into()),
            ),
            kafka_brokers: std::env::var("KAFKA_BROKERS")
                .unwrap_or_else(|_| "localhost:9092".into()),
            command_topic: std::env::var("PDM_COMMAND_TOPIC")
                .unwrap_or_else(|_| "pdm-commands".into()),
            event_topic: std::env::var("PDM_EVENT_TOPIC")
                .unwrap_or_else(|_| "pdm-events".into()),
            consumer_group: std::env::var("KAFKA_CONSUMER_GROUP")
                .unwrap_or_else(|_| "pdm-native-workers".into()),
            inference_interval_secs: std::env::var("INFERENCE_INTERVAL_SECS")
                .unwrap_or_else(|_| "5".into())
                .parse()
                .unwrap_or(5),
            anomaly_interval_secs: std::env::var("ANOMALY_INTERVAL_SECS")
                .unwrap_or_else(|_| "86400".into())
                .parse()
                .unwrap_or(86400),
        }
    }
}
