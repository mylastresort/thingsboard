use anyhow::Result;
use kafka::consumer::Consumer;
use serde::Deserialize;
use tracing::{info, warn};

use crate::config::Config;

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub enum CommandType {
    TRAIN,
    INFER,
    STOP,
    PAUSE,
    UNPAUSE,
}

#[derive(Debug, Clone, Deserialize, PartialEq)]
pub enum ModelType {
    ANOMALY,
    FORECAST,
    BOTH,
}

#[derive(Debug, Clone, Deserialize)]
pub struct PdmCommand {
    pub command_type: CommandType,
    pub forecast_id: String,
    pub model_type: Option<ModelType>,
    pub device_id: Option<String>,
    pub timestamp: i64,
    pub command_id: Option<String>,
}

pub fn create_consumer(config: &Config) -> Result<Consumer> {
    let hosts: Vec<String> = config.kafka_brokers.split(',').map(String::from).collect();
    let consumer = Consumer::from_hosts(hosts)
        .with_topic(config.command_topic.clone())
        .with_group(config.consumer_group.clone())
        .with_fallback_offset(kafka::client::FetchOffset::Earliest)
        .create()?;

    info!("Subscribed to command topic: {}", config.command_topic);
    Ok(consumer)
}

pub fn parse_command(payload: &[u8]) -> Result<PdmCommand> {
    let cmd: PdmCommand = serde_json::from_slice(payload)?;
    Ok(cmd)
}

pub fn poll_message(consumer: &mut Consumer) -> Option<(String, Vec<u8>)> {
    match consumer.poll() {
        Err(e) => {
            warn!("Kafka poll error: {}", e);
            None
        }
        Ok(mss) => {
            for ms in mss.iter() {
                let topic = ms.topic().to_string();
                for msg in ms.messages() {
                    let payload = msg.value.to_vec();
                    consumer.consume_messageset(ms).ok();
                    return Some((topic.clone(), payload));
                }
            }
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_command() {
        let json = r#"{
            "command_type": "TRAIN",
            "forecast_id": "test-123",
            "model_type": "BOTH",
            "device_id": "device-1",
            "timestamp": 1700000000000,
            "command_id": "cmd-1"
        }"#;
        let cmd = parse_command(json.as_bytes()).unwrap();
        assert_eq!(cmd.command_type, CommandType::TRAIN);
        assert_eq!(cmd.forecast_id, "test-123");
    }
}
