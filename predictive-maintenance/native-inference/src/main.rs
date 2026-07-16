pub mod feature_cache;

use feature_cache::FeatureCacheClient;
use tracing::info;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".parse().unwrap()),
        )
        .init();

    let redis_url = std::env::var("REDIS_URL").unwrap_or_else(|_| "redis://redis:6379/0".to_string());
    let prefix = std::env::var("PDM_FEATURE_PREFIX").unwrap_or_else(|_| "pdm:features".to_string());

    let cache = FeatureCacheClient::new(&redis_url, &prefix).await?;
    info!("Feature cache client connected to {redis_url}");

    let device_id = std::env::var("PDM_DEVICE_ID").unwrap_or_else(|_| "test-device".to_string());
    match cache.get_features(&device_id).await? {
        Some(features) => info!(device_id, ?features, "Cached features loaded"),
        None => info!(device_id, "No cached features found"),
    }

    Ok(())
}
