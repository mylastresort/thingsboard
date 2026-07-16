use anyhow::Result;
use kafka::producer::{Record, RequiredAcks};
use serde::Serialize;
use std::time::Duration;
use tracing::{debug, info};

use crate::config::Config;

pub use kafka::producer::Producer as KafkaProducer;

#[derive(Debug, Clone, Serialize)]
pub enum EventType {
    PROGRESS,
    PREDICTION,
    ALARM,
    LOG,
}

#[derive(Debug, Clone, Serialize)]
pub struct PdmEvent {
    pub event_type: EventType,
    pub forecast_id: String,
    pub model_id: String,
    pub iteration: Option<i32>,
    pub timestamp: i64,
    pub progress: Option<ProgressPayload>,
    pub prediction: Option<PredictionPayload>,
    pub alarm: Option<AlarmPayload>,
    pub log: Option<LogPayload>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProgressPayload {
    pub step: String,
    pub message: String,
    pub percent: i32,
}

#[derive(Debug, Clone, Serialize)]
pub struct PredictionPayload {
    pub model_type: String,
    pub sensor: Option<String>,
    pub result_json: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AlarmPayload {
    pub device_id: String,
    pub severity: String,
    pub confidence_score: f64,
    pub details_json: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct LogPayload {
    pub level: String,
    pub source: String,
    pub message: String,
}

pub fn create_producer(config: &Config) -> Result<KafkaProducer> {
    let hosts: Vec<String> = config.kafka_brokers.split(',').map(String::from).collect();
    let producer = KafkaProducer::from_hosts(hosts)
        .with_ack_timeout(Duration::from_secs(5))
        .with_required_acks(RequiredAcks::One)
        .create()?;

    info!("Kafka producer created");
    Ok(producer)
}

pub fn publish_event(producer: &mut KafkaProducer, topic: &str, event: &PdmEvent) -> Result<()> {
    let payload = serde_json::to_vec(event)?;

    producer.send(&Record {
        key: event.forecast_id.as_bytes().to_vec(),
        value: payload,
        topic,
        partition: -1,
    })?;

    debug!("Published event to {}", topic);
    Ok(())
}

pub fn publish_prediction(
    producer: &mut KafkaProducer,
    topic: &str,
    forecast_id: &str,
    model_id: &str,
    model_type: &str,
    sensor: Option<&str>,
    result_json: &str,
) -> Result<()> {
    let event = PdmEvent {
        event_type: EventType::PREDICTION,
        forecast_id: forecast_id.to_string(),
        model_id: model_id.to_string(),
        iteration: None,
        timestamp: chrono::Utc::now().timestamp_millis(),
        progress: None,
        prediction: Some(PredictionPayload {
            model_type: model_type.to_string(),
            sensor: sensor.map(|s| s.to_string()),
            result_json: result_json.to_string(),
        }),
        alarm: None,
        log: None,
    };

    publish_event(producer, topic, &event)
}

pub fn publish_log(
    producer: &mut KafkaProducer,
    topic: &str,
    forecast_id: &str,
    model_id: &str,
    level: &str,
    source: &str,
    message: &str,
) -> Result<()> {
    let event = PdmEvent {
        event_type: EventType::LOG,
        forecast_id: forecast_id.to_string(),
        model_id: model_id.to_string(),
        iteration: None,
        timestamp: chrono::Utc::now().timestamp_millis(),
        progress: None,
        prediction: None,
        alarm: None,
        log: Some(LogPayload {
            level: level.to_string(),
            source: source.to_string(),
            message: message.to_string(),
        }),
    };

    publish_event(producer, topic, &event)
}
