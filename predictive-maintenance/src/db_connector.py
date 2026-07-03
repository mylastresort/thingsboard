"""
Database Connector for Predictive Maintenance

READ-ONLY access to ThingsBoard database.
All write operations are handled by ThingsBoard Java backend.
This module only fetches data for ML model training.
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from src.logger import logger  # Global logger

# Database configuration
DB_NAME = os.getenv("POSTGRES_DB", "thingsboard")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# ThingsBoard connection (for telemetry/devices)
THINGSBOARD_DB_URL = os.getenv(
    "THINGSBOARD_DB_URL",
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
)

# Custom database connection for local configuration and models
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    THINGSBOARD_DB_URL,
)

# Create the engine with connection pooling disabled for read-only operations
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,  # No connection pooling for read-only
    echo=False,
)

tb_engine = create_engine(
    THINGSBOARD_DB_URL,
    poolclass=NullPool,
    echo=False,
)

# Create a session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_connection():
    """Get database connection for raw SQL queries to local config DB"""
    return engine.connect()


def get_tb_db_connection():
    """Get database connection for raw SQL queries to Thingsboard DB"""
    return tb_engine.connect()


def fetch_device_telemetry(
    device_id: str,
    start_time: datetime,
    end_time: datetime,
    keys: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Fetch telemetry data from ThingsBoard ts_kv table.

    ThingsBoard stores time-series data in ts_kv table with structure:
    - entity_id: Device UUID
    - key: Telemetry key (sensor name)
    - ts: Timestamp in milliseconds
    - bool_v, str_v, long_v, dbl_v: Values by type

    Args:
        device_id: Device UUID
        start_time: Start timestamp
        end_time: End timestamp
        keys: Optional list of telemetry keys to fetch

    Returns:
        DataFrame with columns: timestamp, key, value
    """
    try:
        # Convert timestamps to milliseconds (ThingsBoard format)
        start_ts = int(start_time.timestamp() * 1000)
        end_ts = int(end_time.timestamp() * 1000)

        # Build query
        query = """
        SELECT 
            ts,
            key,
            COALESCE(dbl_v, long_v, bool_v::int, str_v::float) as value
        FROM ts_kv
        WHERE entity_id = :device_id
            AND ts >= :start_ts
            AND ts <= :end_ts
        """

        if keys:
            query += " AND key = ANY(:keys)"

        query += " ORDER BY ts ASC, key"

        params = {"device_id": device_id, "start_ts": start_ts, "end_ts": end_ts}

        if keys:
            params["keys"] = keys

        # Execute query
        with get_tb_db_connection() as conn:
            df = pd.read_sql(text(query), conn, params=params)

        # Convert timestamp from milliseconds to datetime
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["ts"], unit="ms")
            df = df.drop("ts", axis=1)

        return df

    except Exception as e:
        logger.error(f"Error fetching device telemetry: {e}")
        raise


def fetch_latest_telemetry(device_id: str, keys: Optional[List[str]] = None) -> Dict[str, float]:
    """
    Fetch latest telemetry values from ThingsBoard ts_kv_latest table.

    Args:
        device_id: Device UUID
        keys: Optional list of telemetry keys

    Returns:
        Dictionary mapping key to value
    """
    try:
        query = """
        SELECT 
            key,
            COALESCE(dbl_v, long_v, bool_v::int, str_v::float) as value
        FROM ts_kv_latest
        WHERE entity_id = :device_id
        """

        if keys:
            query += " AND key = ANY(:keys)"

        params = {"device_id": device_id}
        if keys:
            params["keys"] = keys

        with get_tb_db_connection() as conn:
            result = conn.execute(text(query), params)
            return {row.key: row.value for row in result}

    except Exception as e:
        logger.error(f"Error fetching latest telemetry: {e}")
        raise


def fetch_device_sensors_for_training(
    device_id: str, start_time: datetime, end_time: datetime, expected_sensors: int = 48
) -> pd.DataFrame:
    """
    Fetch sensor data formatted for ML model training.

    Returns a DataFrame with:
    - timestamp column
    - 48 sensor columns (sensor_00 to sensor_47)

    Args:
        device_id: Device UUID
        start_time: Start timestamp
        end_time: End timestamp
        expected_sensors: Number of expected sensors (default: 48)

    Returns:
        DataFrame with timestamp and sensor_XX columns
    """
    try:
        # Fetch all telemetry
        df = fetch_device_telemetry(device_id, start_time, end_time)

        if df.empty:
            logger.warning(f"No telemetry data found for device {device_id}")
            return pd.DataFrame()

        # Pivot to wide format (one column per sensor)
        df_pivot = df.pivot(index="timestamp", columns="key", values="value")
        df_pivot = df_pivot.reset_index()

        # Ensure we have sensor_00 to sensor_47 columns
        for i in range(expected_sensors):
            col_name = f"sensor_{i:02d}"
            if col_name not in df_pivot.columns:
                logger.warning(f"Missing {col_name} for device {device_id}, filling with NaN")
                df_pivot[col_name] = None

        # Select only sensor columns in order
        sensor_cols = [f"sensor_{i:02d}" for i in range(expected_sensors)]
        df_result = df_pivot[["timestamp"] + sensor_cols].copy()

        # Forward fill missing values
        df_result = df_result.fillna(method="ffill").fillna(method="bfill")

        return df_result

    except Exception as e:
        logger.error(f"Error fetching device sensors for training: {e}")
        raise


def fetch_device_failures(
    device_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> pd.DataFrame:
    """
    Fetch device failure events from ThingsBoard alarm table.

    ThingsBoard stores alarms/failures in the alarm table.

    Args:
        device_id: Device UUID
        start_time: Optional start timestamp
        end_time: Optional end timestamp

    Returns:
        DataFrame with failure information
    """
    try:
        query = """
        SELECT 
            created_time,
            severity,
            status,
            type as alarm_type,
            start_ts,
            end_ts,
            ack_ts,
            clear_ts
        FROM alarm
        WHERE originator_id = :device_id
        """

        params = {"device_id": device_id}

        if start_time:
            query += " AND created_time >= :start_time"
            params["start_time"] = int(start_time.timestamp() * 1000)

        if end_time:
            query += " AND created_time <= :end_time"
            params["end_time"] = int(end_time.timestamp() * 1000)

        query += " ORDER BY created_time DESC"

        with get_tb_db_connection() as conn:
            df = pd.read_sql(text(query), conn, params=params)

        # Convert timestamps
        if not df.empty:
            for col in ["created_time", "start_ts", "end_ts", "ack_ts", "clear_ts"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], unit="ms", errors="coerce")

        return df

    except Exception as e:
        logger.error(f"Error fetching device failures: {e}")
        raise


def fetch_all_devices(device_type: Optional[str] = None) -> List[Dict[str, str]]:
    """
    Fetch all devices from ThingsBoard device table.

    Args:
        device_type: Optional filter by device type

    Returns:
        List of device dictionaries with id, name, type, label
    """
    try:
        query = """
        SELECT 
            id,
            name,
            type,
            label
        FROM device
        WHERE 1=1
        """

        params = {}

        if device_type:
            query += " AND type = :device_type"
            params["device_type"] = device_type

        with get_tb_db_connection() as conn:
            result = conn.execute(text(query), params)
            return [
                {
                    "id": str(row.id),
                    "name": row.name,
                    "type": row.type,
                    "label": row.label,
                }
                for row in result
            ]

    except Exception as e:
        logger.error(f"Error fetching devices: {e}")
        raise


def create_training_dataset_for_anomaly(
    device_id: str, days_back: int = 90, include_failures: bool = True
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """
    Create a complete training dataset for anomaly detection.

    Args:
        device_id: Device UUID
        days_back: Number of days of historical data
        include_failures: Whether to include failure labels

    Returns:
        Tuple of (features_df, labels_series)
        - features_df: DataFrame with sensor_00 to sensor_47 columns
        - labels_series: Series with failure labels (if include_failures=True)
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)

        # Fetch sensor data
        logger.info(f"Fetching {days_back} days of sensor data for device {device_id}")
        df = fetch_device_sensors_for_training(device_id, start_time, end_time)

        if df.empty:
            logger.warning(f"No training data available for device {device_id}")
            return pd.DataFrame(), None

        # Fetch failures if requested
        labels = None
        if include_failures:
            logger.info(f"Fetching failure data for device {device_id}")
            failures_df = fetch_device_failures(device_id, start_time, end_time)

            if not failures_df.empty:
                # Create binary labels: 1 if failure within next 24 hours, 0 otherwise
                df["failure_within_24h"] = 0

                for _, failure in failures_df.iterrows():
                    failure_time = failure["created_time"]
                    # Mark 24 hours before failure as positive
                    mask = (df["timestamp"] >= failure_time - timedelta(hours=24)) & (
                        df["timestamp"] <= failure_time
                    )
                    df.loc[mask, "failure_within_24h"] = 1

                labels = df["failure_within_24h"]
                df = df.drop("failure_within_24h", axis=1)

        # Drop timestamp for training
        features = df.drop("timestamp", axis=1)

        logger.info(
            f"Created training dataset: {len(features)} samples, {len(features.columns)} features"
        )

        return features, labels

    except Exception as e:
        logger.error(f"Error creating training dataset: {e}")
        raise


def create_training_dataset_for_forecast(
    device_id: str, sensor_key: str, days_back: int = 90
) -> pd.DataFrame:
    """
    Create a training dataset for time-series forecasting.

    Args:
        device_id: Device UUID
        sensor_key: Which sensor to forecast (e.g., 'sensor_00')
        days_back: Number of days of historical data

    Returns:
        DataFrame with 'ds' (timestamp) and 'y' (value) columns (Prophet format)
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days_back)

        logger.info(f"Fetching {days_back} days of data for sensor {sensor_key}")
        df = fetch_device_telemetry(device_id, start_time, end_time, keys=[sensor_key])

        if df.empty:
            logger.warning(f"No data available for {sensor_key}")
            return pd.DataFrame()

        # Format for Prophet: 'ds' and 'y' columns
        df_forecast = pd.DataFrame({"ds": df["timestamp"], "y": df["value"]})

        logger.info(f"Created forecast dataset: {len(df_forecast)} samples")

        return df_forecast

    except Exception as e:
        logger.error(f"Error creating forecast dataset: {e}")
        raise


def setup_model_database():
    """
    Create custom database tables for the model server if they don't exist.
    """
    with get_db_connection() as conn:
        # Predictive Maintenance Config Table
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS predictive_maintenance_config (
                id uuid NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
                name varchar(255) NOT NULL,
                created_time bigint NOT NULL,
                tenant_id uuid,
                device_id uuid,
                attributes jsonb,
                forecast_algorithm varchar(255),
                forecast_start_date bigint,
                forecast_end_date bigint,
                anomaly_algorithm varchar(255),
                anomaly_start_date bigint,
                anomaly_end_date bigint,
                view_preferences jsonb,
                additional_data jsonb
            );
        """)
        )

        # Model Logs Table
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS model_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                created_time BIGINT NOT NULL,
                model_id VARCHAR(255) NOT NULL,
                tenant_id UUID,
                device_id UUID,
                timestamp BIGINT NOT NULL,
                log_level VARCHAR(20) NOT NULL,
                message TEXT NOT NULL,
                source VARCHAR(100),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        )

        # Predictive Model Load Model Config Table
        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS predictive_model_load_model_config (
                name VARCHAR(255) PRIMARY KEY,
                config JSONB
            );
        """)
        )
        conn.commit()
