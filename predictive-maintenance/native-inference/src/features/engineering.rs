use polars::prelude::*;
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct TelemetryPoint {
    pub timestamp: i64,
    pub values: HashMap<String, f64>,
}

pub struct AnomalyFeatureEngineer {
    sensors: Vec<String>,
    error_keys: Vec<String>,
    component_keys: Vec<String>,
}

impl AnomalyFeatureEngineer {
    pub fn new() -> Self {
        Self {
            sensors: vec![
                "volt".into(),
                "rotate".into(),
                "pressure".into(),
                "vibration".into(),
            ],
            error_keys: vec![
                "error1".into(),
                "error2".into(),
                "error3".into(),
                "error4".into(),
                "error5".into(),
            ],
            component_keys: vec![
                "comp1".into(),
                "comp2".into(),
                "comp3".into(),
                "comp4".into(),
            ],
        }
    }

    /// Build a polars DataFrame from telemetry history and compute rolling features.
    pub fn extract_features(
        &self,
        telemetry_history: &[TelemetryPoint],
        error_counts: &HashMap<String, u32>,
        component_days: &HashMap<String, f64>,
        machine_age: f64,
    ) -> Vec<f32> {
        if telemetry_history.is_empty() {
            return vec![0.0; self.feature_count()];
        }

        let mut features = Vec::with_capacity(self.feature_count());

        // Rolling stats for each sensor using polars Series.rolling_mean / rolling_std
        for sensor in &self.sensors {
            let values: Vec<f64> = telemetry_history
                .iter()
                .map(|p| p.values.get(sensor).copied().unwrap_or(0.0))
                .collect();

            let s = Series::new(sensor.as_str().into(), values.as_slice());

            let opts_3 = RollingOptionsFixedWindow {
                window_size: 3,
                min_periods: 1,
                ..Default::default()
            };
            let opts_24 = RollingOptionsFixedWindow {
                window_size: 24,
                min_periods: 1,
                ..Default::default()
            };

            let mean_3h = s.rolling_mean(opts_3.clone()).unwrap_or(Series::new("".into(), &[0.0]));
            let sd_3h = s.rolling_var(opts_3).unwrap_or(Series::new("".into(), &[0.0]));
            let mean_24h = s.rolling_mean(opts_24.clone()).unwrap_or(Series::new("".into(), &[0.0]));
            let sd_24h = s.rolling_var(opts_24).unwrap_or(Series::new("".into(), &[0.0]));

            features.push(mean_3h.f64().unwrap().last().unwrap_or(0.0) as f32);
            // std = sqrt(var)
            features.push(sd_3h.f64().unwrap().last().map(|v| v.sqrt()).unwrap_or(0.0) as f32);
            features.push(mean_24h.f64().unwrap().last().unwrap_or(0.0) as f32);
            features.push(sd_24h.f64().unwrap().last().map(|v| v.sqrt()).unwrap_or(0.0) as f32);
        }

        // Error counts
        for err_key in &self.error_keys {
            features.push(error_counts.get(err_key).copied().unwrap_or(0) as f32);
        }

        // Component days since replacement
        for comp in &self.component_keys {
            features.push(component_days.get(comp).copied().unwrap_or(999.0) as f32);
        }

        // Machine age
        features.push(machine_age as f32);

        features
    }

    pub fn feature_count(&self) -> usize {
        self.sensors.len() * 4 + self.error_keys.len() + self.component_keys.len() + 1
    }
}

pub struct ForecastFeatureEngineer {
    lookback_window: usize,
}

impl ForecastFeatureEngineer {
    pub fn new(lookback_window: usize) -> Self {
        Self { lookback_window }
    }

    /// Create lag + rolling features using polars Series operations.
    pub fn create_lag_features(&self, values: &[f64]) -> Vec<f32> {
        if values.is_empty() {
            return vec![0.0; self.feature_count()];
        }

        let s = Series::new("value".into(), values);
        let mut features = Vec::with_capacity(self.feature_count());

        // Lag features
        for i in 1..=self.lookback_window {
            let idx = values.len().saturating_sub(i);
            features.push(values[idx] as f32);
        }

        // Rolling mean / var for windows 6, 12, 24
        for window in &[6, 12, 24] {
            let w = (*window).min(values.len());
            let opts = RollingOptionsFixedWindow {
                window_size: w,
                min_periods: 1,
                ..Default::default()
            };

            let mean = s.rolling_mean(opts.clone()).unwrap_or(Series::new("".into(), &[0.0]));
            let var = s.rolling_var(opts).unwrap_or(Series::new("".into(), &[0.0]));

            features.push(mean.f64().unwrap().last().unwrap_or(0.0) as f32);
            features.push(var.f64().unwrap().last().map(|v| v.sqrt()).unwrap_or(0.0) as f32);
        }

        // Time-based placeholders (filled by caller with real timestamps)
        features.extend_from_slice(&[0.0, 0.0, 0.0, 0.0]);

        features
    }

    pub fn feature_count(&self) -> usize {
        self.lookback_window + 6 + 4
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_feature_extraction() {
        let engineer = AnomalyFeatureEngineer::new();
        let telemetry = vec![TelemetryPoint {
            timestamp: 0,
            values: [
                ("volt".into(), 100.0),
                ("rotate".into(), 200.0),
                ("pressure".into(), 50.0),
                ("vibration".into(), 10.0),
            ]
            .into_iter()
            .collect(),
        }];

        let error_counts = HashMap::new();
        let component_days = HashMap::new();

        let features = engineer.extract_features(&telemetry, &error_counts, &component_days, 5.0);
        assert_eq!(features.len(), 26);
    }

    #[test]
    fn test_rolling_polars() {
        let values = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let s = Series::new("v".into(), values.as_slice());
        let opts = RollingOptionsFixedWindow {
            window_size: 3,
            min_periods: 1,
            ..Default::default()
        };
        let result = s.rolling_mean(opts).unwrap();
        let f64_vals: Vec<f64> = result.f64().unwrap().into_no_null_iter().collect();
        assert!((f64_vals[0] - 1.0).abs() < 1e-10);
        assert!((f64_vals[2] - 2.0).abs() < 1e-10);
        assert!((f64_vals[4] - 4.0).abs() < 1e-10);
    }

    #[test]
    fn test_forecast_features() {
        let engineer = ForecastFeatureEngineer::new(20);
        let values: Vec<f64> = (0..50).map(|i| i as f64).collect();
        let features = engineer.create_lag_features(&values);
        assert_eq!(features.len(), 30); // 20 lags + 6 rolling + 4 time
    }
}
