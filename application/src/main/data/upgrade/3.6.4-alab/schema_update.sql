--
-- Copyright © 2016-2024 The Thingsboard Authors
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--     http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.
--

-- ==============================================================================
-- PREDICTIVE MAINTENANCE CONFIG TABLE
-- Stores predictive maintenance configurations including forecast and anomaly detection
-- algorithms with their date ranges for each device
-- ==============================================================================
CREATE TABLE IF NOT EXISTS predictive_maintenance_config (
    id uuid NOT NULL CONSTRAINT predictive_maintenance_config_pkey PRIMARY KEY,
    name varchar(255) NOT NULL,
    created_time bigint NOT NULL,
    tenant_id uuid NOT NULL CONSTRAINT fk_pm_config_tenant_id REFERENCES tenant (id) ON DELETE CASCADE,
    device_id uuid NOT NULL CONSTRAINT fk_pm_config_device_id REFERENCES device (id) ON DELETE CASCADE,
    attributes jsonb NOT NULL,
    forecast_algorithm varchar(255) NOT NULL DEFAULT 'ARIMA',
    forecast_start_date bigint NOT NULL DEFAULT 0,
    forecast_end_date bigint NOT NULL DEFAULT 0,
    anomaly_algorithm varchar(255) NOT NULL DEFAULT 'THRESHOLD',
    anomaly_start_date bigint NOT NULL DEFAULT 0,
    anomaly_end_date bigint NOT NULL DEFAULT 0,
    view_preferences jsonb DEFAULT '{"selectedViews": ["forecast", "anomalies"]}'::jsonb
);

ALTER TABLE predictive_maintenance_config
ADD COLUMN IF NOT EXISTS additional_data jsonb DEFAULT '{}'::jsonb;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_pm_config_tenant_id ON predictive_maintenance_config (tenant_id);

CREATE INDEX IF NOT EXISTS idx_pm_config_device_id ON predictive_maintenance_config (device_id);

CREATE INDEX IF NOT EXISTS idx_pm_config_created_time ON predictive_maintenance_config (created_time DESC);

-- ==============================================================================
-- CLAIM TABLE
-- ==============================================================================
CREATE TABLE IF NOT EXISTS claim (
    id uuid NOT NULL CONSTRAINT claims_pkey PRIMARY KEY,
    body varchar(255) NOT NULL,
    created_time bigint NOT NULL,
    tenant_id uuid NOT NULL CONSTRAINT fk_claims_tenant_id REFERENCES tenant (id) ON DELETE CASCADE,
    done BOOLEAN DEFAULT FALSE,
    name varchar(255) NOT NULL
);

ALTER TABLE claim
ADD COLUMN IF NOT EXISTS assignee_id uuid CONSTRAINT fk_claims_assignee_id REFERENCES tb_user (id);

ALTER TABLE claim
ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '[]'::jsonb;

-- ==============================================================================
-- MODEL LOGS TABLE - not used now, reserved for future use
-- Stores execution logs from predictive maintenance models
-- Supports time window filtering and pagination
-- ==============================================================================
CREATE TABLE IF NOT EXISTS model_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    created_time BIGINT NOT NULL, -- ThingsBoard standard created_time in epoch milliseconds
    model_id VARCHAR(255) NOT NULL, -- References predictive_maintenance_config.id
    tenant_id UUID NOT NULL CONSTRAINT fk_model_logs_tenant_id REFERENCES tenant (id) ON DELETE CASCADE,
    device_id UUID NOT NULL CONSTRAINT fk_model_logs_device_id REFERENCES device (id) ON DELETE CASCADE,
    timestamp BIGINT NOT NULL, -- Epoch milliseconds for consistency with ThingsBoard
    log_level VARCHAR(20) NOT NULL, -- INFO, WARN, ERROR
    message TEXT NOT NULL,
    source VARCHAR(100), -- 'activation', 'ForecastModel', 'AnomalyPredictor'
    metadata JSONB, -- Additional context (stack trace, metrics, etc.)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Add created_time column if it doesn't exist (for existing tables)
ALTER TABLE model_logs ADD COLUMN IF NOT EXISTS created_time BIGINT;

-- Update created_time for existing rows where it's null (use timestamp as fallback)
UPDATE model_logs
SET
    created_time = timestamp
WHERE
    created_time IS NULL;

-- Make created_time NOT NULL after populating
ALTER TABLE model_logs ALTER COLUMN created_time SET NOT NULL;

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_model_logs_model_id ON model_logs (model_id);

CREATE INDEX IF NOT EXISTS idx_model_logs_tenant_id ON model_logs (tenant_id);

CREATE INDEX IF NOT EXISTS idx_model_logs_device_id ON model_logs (device_id);

CREATE INDEX IF NOT EXISTS idx_model_logs_timestamp ON model_logs (timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_model_logs_model_timestamp ON model_logs (model_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_model_logs_level ON model_logs (log_level);

CREATE INDEX IF NOT EXISTS idx_model_logs_source ON model_logs (source);

-- Composite index for common query pattern: model + time window + level
CREATE INDEX IF NOT EXISTS idx_model_logs_query ON model_logs (
    model_id,
    timestamp DESC,
    log_level
);

-- ==============================================================================
-- UPDATE PREDICTIVE_MAINTENANCE_CONFIG TABLE
-- Add log settings to view_preferences
-- ==============================================================================
DO $$
BEGIN
    -- Update existing records to include default log settings if not present
    UPDATE predictive_maintenance_config
    SET view_preferences = jsonb_set(
        COALESCE(view_preferences, '{}'::jsonb),
        '{logSettings}',
        '{
            "timeWindow": 3600000,
            "pageSize": 50,
            "autoRefresh": true,
            "refreshInterval": 5000
        }'::jsonb,
        true
    )
    WHERE NOT (view_preferences ? 'logSettings');
END $$;

-- ==============================================================================
-- LOG CLEANUP FUNCTION
-- Automatically delete logs older than retention period
-- ==============================================================================
CREATE OR REPLACE FUNCTION cleanup_old_model_logs(retention_days INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
    cutoff_timestamp BIGINT;
BEGIN
    -- Calculate cutoff timestamp (retention_days ago in epoch milliseconds)
    cutoff_timestamp := (EXTRACT(EPOCH FROM NOW() - (retention_days || ' days')::INTERVAL) * 1000)::BIGINT;
    
    -- Delete old logs
    DELETE FROM model_logs WHERE timestamp < cutoff_timestamp;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- SCHEDULED CLEANUP (Optional - requires pg_cron extension)
-- ==============================================================================
-- Uncomment if pg_cron is installed:
-- SELECT cron.schedule('cleanup-model-logs', '0 2 * * *',
--     'SELECT cleanup_old_model_logs(30);'
-- );

-- ==============================================================================
-- PARTITIONING (Optional - for high-volume deployments)
-- ==============================================================================
-- For very high log volumes, consider partitioning by timestamp
-- Example: Create monthly partitions
--
-- ALTER TABLE model_logs RENAME TO model_logs_template;
--
-- CREATE TABLE model_logs (
--     LIKE model_logs_template INCLUDING ALL
-- ) PARTITION BY RANGE (timestamp);
--
-- CREATE TABLE model_logs_2025_10 PARTITION OF model_logs
--     FOR VALUES FROM (1727740800000) TO (1730419200000);

-- ==============================================================================
-- PREDICTIVE MAINTENANCE SCHEMA
-- ==============================================================================
-- This schema extends ThingsBoard's existing device table with predictive
-- maintenance specific tables for sensor readings, failures, and ML models
--
-- NOTE: We reuse ThingsBoard's 'device' table instead of creating 'machines'
-- The device table already contains: id, name, type, label, tenant_id, customer_id
-- Additional machine metadata can be stored in device.device_data (jsonb)
-- ==============================================================================

-- ==============================================================================
-- SENSOR DATA STORAGE
-- ==============================================================================
-- NOTE: We use ThingsBoard's existing telemetry tables instead of custom sensor tables:
--   - ts_kv: Time-series telemetry data (partitioned by timestamp)
--     Columns: entity_id (device), key (sensor key_id from key_dictionary), ts, dbl_v, long_v, etc.
--   - ts_kv_latest: Latest telemetry values per key
--     Columns: entity_id, key, ts, dbl_v, long_v, bool_v, str_v, json_v
--   - key_dictionary: Maps sensor keys (strings) to integer key_ids
--     Columns: key (varchar), key_id (integer)
--   - attribute_kv: Device attributes (sensor configuration, thresholds, metadata)
--     Columns: entity_id, attribute_type, attribute_key, bool_v, str_v, long_v, dbl_v, json_v
--
-- Sensor Configuration:
--   Store sensor metadata (type, unit, thresholds, position) as device attributes in attribute_kv table
--   Example attributes: "sensor_00_type", "sensor_00_unit", "sensor_00_min", "sensor_00_max"
--
-- Sensor Readings:
--   All sensor telemetry is automatically stored in ts_kv and ts_kv_latest tables
--   Query using device.id (entity_id) and key_dictionary.key_id
-- ==============================================================================

-- ==============================================================================
-- 1. DEVICE_ERRORS TABLE
-- Stores device error events that may precede failures
-- References ThingsBoard's device table
-- ==============================================================================
CREATE TABLE IF NOT EXISTS device_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    device_id UUID NOT NULL, -- References device(id) from ThingsBoard
    error_time TIMESTAMP NOT NULL,
    error_code VARCHAR(100) NOT NULL, -- Error code/ID (e.g., error1, error2)
    error_type VARCHAR(255), -- Type: Sensor, Communication, Hardware, Software
    error_severity VARCHAR(50), -- Critical, Major, Minor, Warning
    error_description TEXT,
    component VARCHAR(255), -- Which component reported the error
    recovery_time TIMESTAMP, -- When error was cleared/recovered
    was_auto_recovered BOOLEAN DEFAULT FALSE,
    led_to_failure BOOLEAN DEFAULT FALSE, -- Did this error lead to a failure?
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(), -- Additional timestamp for logging purposes
    CONSTRAINT fk_device_errors_device FOREIGN KEY (device_id) REFERENCES device (id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_errors_device_id ON device_errors (device_id);

CREATE INDEX IF NOT EXISTS idx_errors_error_time ON device_errors (error_time DESC);

CREATE INDEX IF NOT EXISTS idx_errors_error_code ON device_errors (error_code);

CREATE INDEX IF NOT EXISTS idx_errors_error_type ON device_errors (error_type);

-- ==============================================================================
-- 2. DEVICE_FAILURES TABLE
-- Stores historical failure events for supervised learning
-- References ThingsBoard's device table
-- ==============================================================================
CREATE TABLE IF NOT EXISTS device_failures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    device_id UUID NOT NULL, -- References device(id) from ThingsBoard
    failure_time TIMESTAMP NOT NULL,
    detection_time TIMESTAMP,
    resolved_time TIMESTAMP,
    failure_type VARCHAR(255) NOT NULL, -- Type: Bearing, Motor, Overheating, etc.
    failure_severity VARCHAR(50), -- Critical, Major, Minor
    failure_description TEXT,
    root_cause VARCHAR(255) NOT NULL, -- Root cause if known
    downtime_hours FLOAT,
    repair_cost FLOAT,
    replaced_parts JSONB, -- List of replaced parts
    maintenance_actions JSONB, -- Actions taken
    was_predicted BOOLEAN DEFAULT FALSE, -- Was this predicted by ML?
    prediction_lead_time_hours FLOAT, -- How early was it predicted?
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(), -- Additional timestamp for logging purposes
    CONSTRAINT fk_device_failures_device FOREIGN KEY (device_id) REFERENCES device (id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_failures_device_id ON device_failures (device_id);

CREATE INDEX IF NOT EXISTS idx_failures_failure_time ON device_failures (failure_time DESC);

CREATE INDEX IF NOT EXISTS idx_failures_failure_type ON device_failures (failure_type);

-- ==============================================================================
-- 3. DEVICE_MAINTENANCE TABLE
-- Stores scheduled and unscheduled maintenance activities
-- References ThingsBoard's device table
-- ==============================================================================
CREATE TABLE IF NOT EXISTS device_maintenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    device_id UUID NOT NULL, -- References device(id) from ThingsBoard
    maintenance_type VARCHAR(100) NOT NULL, -- Scheduled, Unscheduled, Predictive
    maintenance_date TIMESTAMP NOT NULL,
    duration_hours FLOAT,
    cost FLOAT,
    technician VARCHAR(255),
    description TEXT,
    parts_replaced VARCHAR(255) NOT NULL,
    actions_performed JSONB,
    next_maintenance_date TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(), -- Additional timestamp for logging purposes
    CONSTRAINT fk_device_maintenance_device FOREIGN KEY (device_id) REFERENCES device (id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_maintenance_device_id ON device_maintenance (device_id);

CREATE INDEX IF NOT EXISTS idx_maintenance_date ON device_maintenance (maintenance_date DESC);

-- ==============================================================================
-- 3. ML_MODELS TABLE
-- Stores metadata about trained ML models
-- References ThingsBoard's device table (device_id can be NULL for global models)
-- ==============================================================================
CREATE TABLE IF NOT EXISTS ml_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    model_id VARCHAR(255) UNIQUE NOT NULL, -- forecast_id from the application
    model_name VARCHAR(255) NOT NULL,
    model_type VARCHAR(100) NOT NULL, -- AnomalyPredictor, ForecastModel
    algorithm VARCHAR(100), -- XGBoost, Prophet, etc.
    device_id UUID, -- NULL if model is for all devices
    training_start_time TIMESTAMP,
    training_end_time TIMESTAMP,
    training_data_start TIMESTAMP, -- Data range used for training
    training_data_end TIMESTAMP,
    training_samples INTEGER,
    model_metrics JSONB, -- Accuracy, F1, RMSE, etc.
    model_path VARCHAR(500), -- Path to saved model files
    is_active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_ml_models_device FOREIGN KEY (device_id) REFERENCES device (id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ml_models_model_id ON ml_models (model_id);

CREATE INDEX IF NOT EXISTS idx_ml_models_device_id ON ml_models (device_id);

CREATE INDEX IF NOT EXISTS idx_ml_models_is_active ON ml_models (is_active);

-- ==============================================================================
-- 4. PREDICTIONS TABLE
-- Stores predictions made by ML models
-- References ThingsBoard's device table
-- ==============================================================================
CREATE TABLE IF NOT EXISTS predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    model_id UUID NOT NULL REFERENCES predictive_maintenance_config (id) ON DELETE CASCADE,
    created_time BIGINT NOT NULL, -- ThingsBoard standard created_time in epoch milliseconds
    created_at TIMESTAMP DEFAULT NOW(),
    prediction_time TIMESTAMP NOT NULL DEFAULT NOW(),
    prediction_type VARCHAR(100) NOT NULL, -- Anomaly, Forecast, Failure
    prediction_value JSONB
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_predictions_model_id ON predictions (model_id);

CREATE INDEX IF NOT EXISTS idx_predictions_device_id ON predictions (device_id);

CREATE INDEX IF NOT EXISTS idx_predictions_prediction_time ON predictions (prediction_time DESC);

-- ==============================================================================
-- 5. SENSOR_STATISTICS TABLE (Materialized View Alternative)
-- Pre-computed statistics for faster model training
-- References ThingsBoard's device and key_dictionary tables
-- ==============================================================================
CREATE TABLE IF NOT EXISTS sensor_statistics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
    device_id UUID NOT NULL, -- References device(id) from ThingsBoard
    sensor_key_id INTEGER NOT NULL, -- References key_dictionary(key_id) - sensor telemetry key
    sensor_key VARCHAR(255) NOT NULL, -- Sensor key name from key_dictionary(key)
    time_window_start TIMESTAMP NOT NULL,
    time_window_end TIMESTAMP NOT NULL,
    sample_count INTEGER,
    mean_value DOUBLE PRECISION,
    std_dev DOUBLE PRECISION,
    min_value DOUBLE PRECISION,
    max_value DOUBLE PRECISION,
    median_value DOUBLE PRECISION,
    q1_value DOUBLE PRECISION, -- 25th percentile
    q3_value DOUBLE PRECISION, -- 75th percentile
    anomaly_count INTEGER DEFAULT 0,
    computed_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_sensor_statistics_device FOREIGN KEY (device_id) REFERENCES device (id) ON DELETE CASCADE,
    UNIQUE (
        device_id,
        sensor_key_id,
        time_window_start
    )
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_stats_device_id ON sensor_statistics (device_id);

CREATE INDEX IF NOT EXISTS idx_stats_sensor_key_id ON sensor_statistics (sensor_key_id);

CREATE INDEX IF NOT EXISTS idx_stats_time_window ON sensor_statistics (time_window_start DESC);

CREATE INDEX IF NOT EXISTS idx_stats_device_sensor ON sensor_statistics (device_id, sensor_key_id);

-- ==============================================================================
-- VIEWS
-- ==============================================================================

-- View: Latest sensor readings for each device and sensor key
-- Uses ThingsBoard's ts_kv_latest table for telemetry data
CREATE OR REPLACE VIEW latest_sensor_readings AS
SELECT 
    t.entity_id as device_id,
    t.key as sensor_key_id,
    k.key as sensor_key,
    t.ts as timestamp,
    COALESCE(t.dbl_v, t.long_v::double precision) as value,
    t.bool_v,
    t.str_v,
    t.json_v
FROM ts_kv_latest t
JOIN key_dictionary k ON t.key = k.key_id
ORDER BY t.entity_id, t.key;

-- View: Device health summary (using ThingsBoard's device and telemetry tables)
CREATE OR REPLACE VIEW device_health_summary AS
SELECT
    d.id as device_id,
    d.name as device_name,
    d.type as device_type,
    d.label as device_label,
    COUNT(DISTINCT t.key) as sensor_count,
    COUNT(DISTINCT mf.id) as failure_count,
    MAX(mf.failure_time) as last_failure_time,
    MAX(ml.maintenance_date) as last_maintenance_date,
    MAX(t.ts) as last_reading_timestamp
FROM
    device d
    LEFT JOIN ts_kv_latest t ON d.id = t.entity_id
    LEFT JOIN device_failures mf ON d.id = mf.device_id
    LEFT JOIN device_maintenance ml ON d.id = ml.device_id
GROUP BY
    d.id,
    d.name,
    d.type,
    d.label;

-- View: Recent logs per model with aggregated stats
CREATE OR REPLACE VIEW model_logs_summary AS
SELECT
    model_id,
    COUNT(*) as total_logs,
    COUNT(*) FILTER (
        WHERE
            log_level = 'INFO'
    ) as info_count,
    COUNT(*) FILTER (
        WHERE
            log_level = 'WARN'
    ) as warn_count,
    COUNT(*) FILTER (
        WHERE
            log_level = 'ERROR'
    ) as error_count,
    MAX(timestamp) as last_log_timestamp,
    MIN(timestamp) as first_log_timestamp
FROM model_logs
GROUP BY
    model_id;

-- View: Recent errors (last 24 hours)
CREATE OR REPLACE VIEW recent_model_errors AS
SELECT 
    ml.model_id,
    pmc.name as model_name,
    ml.timestamp,
    ml.message,
    ml.source,
    ml.metadata
FROM model_logs ml
JOIN predictive_maintenance_config pmc ON ml.model_id::UUID = pmc.id
WHERE ml.log_level = 'ERROR'
  AND ml.timestamp > (EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours') * 1000)::BIGINT
ORDER BY ml.timestamp DESC;

-- ==============================================================================
-- FUNCTIONS
-- ==============================================================================

-- Function: Update updated_at timestamp automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Triggers for updated_at
-- Note: No trigger needed for device table as it's managed by ThingsBoard core
-- Note: No trigger needed for sensor data as it's stored in ThingsBoard's ts_kv tables

DROP TRIGGER IF EXISTS update_ml_models_updated_at ON ml_models;

CREATE TRIGGER update_ml_models_updated_at BEFORE UPDATE ON ml_models
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==============================================================================
-- SAMPLE QUERIES
-- ==============================================================================

-- Get logs for a specific model in time window with pagination
-- SELECT * FROM model_logs
-- WHERE model_id = 'xxx-xxx-xxx-xxx'
--   AND timestamp BETWEEN ? AND ?
--   AND log_level IN ('INFO', 'WARN', 'ERROR')
-- ORDER BY timestamp DESC
-- LIMIT 50 OFFSET 0;

-- Get logs grouped by source
-- SELECT source, COUNT(*), MAX(timestamp)
-- FROM model_logs
-- WHERE model_id = 'xxx-xxx-xxx-xxx'
-- GROUP BY source;

-- Get error rate over time (hourly buckets)
-- SELECT
--     (timestamp / 3600000) * 3600000 as hour_bucket,
--     COUNT(*) FILTER (WHERE log_level = 'ERROR') as error_count,
--     COUNT(*) as total_count
-- FROM model_logs
-- WHERE model_id = 'xxx-xxx-xxx-xxx'
-- GROUP BY hour_bucket
-- ORDER BY hour_bucket DESC;

alter table model_logs drop column tenant_id;
-- add message title column
alter table model_logs add column if not exists title varchar(255);

alter table device_errors add column if not exists created_time bigint;