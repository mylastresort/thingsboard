use redis::AsyncCommands;
use serde::Deserialize;
use std::collections::HashMap;

/// Pre-computed feature vector from the feature worker's Redis cache.
#[derive(Debug, Clone, Deserialize)]
pub struct CachedFeatures {
    pub features: HashMap<String, f64>,
    pub timestamp: String,
}

/// Client that reads pre-computed feature vectors from Redis.
///
/// Key pattern: `pdm:features:{device_id}`
/// The feature worker writes these, inference reads them.
pub struct FeatureCacheClient {
    conn: redis::aio::ConnectionManager,
    prefix: String,
}

impl FeatureCacheClient {
    pub async fn new(redis_url: &str, prefix: &str) -> Result<Self, redis::RedisError> {
        let client = redis::Client::open(redis_url)?;
        let conn = client.get_connection_manager().await?;
        Ok(Self {
            conn,
            prefix: prefix.to_string(),
        })
    }

    fn key(&self, device_id: &str) -> String {
        format!("{}:{}", self.prefix, device_id)
    }

    /// Fetch the latest cached feature vector for a device.
    pub async fn get_features(
        &self,
        device_id: &str,
    ) -> Result<Option<HashMap<String, f64>>, redis::RedisError> {
        let mut conn = self.conn.clone();
        let raw: Option<String> = conn.get(self.key(device_id)).await?;
        match raw {
            Some(json) => {
                let cached: CachedFeatures = serde_json::from_str(&json)
                    .map_err(|e| redis::RedisError::from((redis::ErrorKind::TypeError, "deserialization", e.to_string())))?;
                Ok(Some(cached.features))
            }
            None => Ok(None),
        }
    }

    /// Fetch features with their timestamp.
    pub async fn get_with_timestamp(
        &self,
        device_id: &str,
    ) -> Result<Option<CachedFeatures>, redis::RedisError> {
        let mut conn = self.conn.clone();
        let raw: Option<String> = conn.get(self.key(device_id)).await?;
        match raw {
            Some(json) => {
                let cached: CachedFeatures = serde_json::from_str(&json)
                    .map_err(|e| redis::RedisError::from((redis::ErrorKind::TypeError, "deserialization", e.to_string())))?;
                Ok(Some(cached))
            }
            None => Ok(None),
        }
    }

    /// Fetch features for multiple devices in a single pipeline.
    pub async fn get_batch(
        &self,
        device_ids: &[&str],
    ) -> Result<HashMap<String, HashMap<String, f64>>, redis::RedisError> {
        let mut conn = self.conn.clone();
        let mut pipe = redis::pipe();
        for did in device_ids {
            pipe.get(self.key(did));
        }
        let results: Vec<Option<String>> = pipe.query_async(&mut conn).await?;

        let mut out = HashMap::new();
        for (did, raw) in device_ids.iter().zip(results) {
            if let Some(json) = raw {
                if let Ok(cached) = serde_json::from_str::<CachedFeatures>(&json) {
                    out.insert(did.to_string(), cached.features);
                }
            }
        }
        Ok(out)
    }

    /// Check if a device has cached features.
    pub async fn exists(&self, device_id: &str) -> Result<bool, redis::RedisError> {
        let mut conn = self.conn.clone();
        let n: i64 = conn.exists(self.key(device_id)).await?;
        Ok(n > 0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_key_construction() {
        let key = format!("{}:{}", "pdm:features", "device-123");
        assert_eq!(key, "pdm:features:device-123");
    }

    #[test]
    fn test_cached_features_deserialize() {
        let json = r#"{"features":{"voltmean_3h":10.5,"age":25},"timestamp":"2024-01-01T00:00:00Z"}"#;
        let cached: CachedFeatures = serde_json::from_str(json).unwrap();
        assert_eq!(cached.features["voltmean_3h"], 10.5);
        assert_eq!(cached.features["age"], 25.0);
        assert_eq!(cached.timestamp, "2024-01-01T00:00:00Z");
    }
}
