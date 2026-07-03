"""
Data Registry - Centralized database access layer for model training data.

This class handles all database operations for fetching training data from ThingsBoard.
Models should use this registry instead of direct database calls.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from src.logger import logger  # Global logger


class DataRegistry:
    """
    Centralized data access layer for model training.

    This class encapsulates all database operations and provides
    meaningful methods for fetching different types of training data.
    """

    def __init__(
        self,
        database_url: str,
        telemetry_keys: List[str] = None,
        error_keys: List[str] = None,
        component_keys: List[str] = None,
    ):
        """
        Initialize the data registry with database connection.

        Args:
            database_url: SQLAlchemy database URL
                         e.g., "postgresql://user:pass@localhost:5432/thingsboard"
            telemetry_keys: List of telemetry keys to fetch (e.g., ['volt', 'rotate', 'pressure', 'vibration'])
            error_keys: List of error keys to track (e.g., ['error1', 'error2', ...])
            component_keys: List of component keys to track (e.g., ['comp1', 'comp2', ...])
        """
        self.database_url = database_url
        self.engine: Optional[Engine] = None

        # Configuration with defaults
        self.telemetry_keys = telemetry_keys or [
            "volt",
            "rotate",
            "pressure",
            "vibration",
        ]
        self.error_keys = error_keys or [
            "error1",
            "error2",
            "error3",
            "error4",
            "error5",
        ]
        self.component_keys = component_keys or ["comp1", "comp2", "comp3", "comp4"]

        self._connect()

        # Resolve key IDs from key_dictionary after connection is established
        # Only telemetry keys need to be resolved - errors/failures/maintenance are in dedicated tables
        self.telemetry_keys_ids = self._get_key_ids(self.telemetry_keys)

    def _connect(self) -> None:
        """Establish database connection."""
        try:
            self.engine = create_engine(self.database_url, echo=False)
        except Exception as e:
            raise

    def _get_key_ids(self, key_names: List[str]) -> List[int]:
        """
        Convert string key names to integer key_ids using key_dictionary.

        Args:
            key_names: List of key names like ['volt', 'rotate', 'pressure']

        Returns:
            List of integer key_ids like [123, 124, 125]
        """
        if not key_names:
            return []

        try:
            with self.engine.connect() as conn:
                # Build parameterized query
                placeholders = ", ".join([f":key_{i}" for i in range(len(key_names))])
                params = {f"key_{i}": key for i, key in enumerate(key_names)}

                query = text(
                    f"""
                    SELECT key, key_id
                    FROM key_dictionary
                    WHERE key IN ({placeholders})
                    ORDER BY key_id
                """
                )

                result = conn.execute(query, params)
                key_map = {row.key: row.key_id for row in result}

                # Return key_ids in the same order as key_names
                key_ids = []
                for key_name in key_names:
                    if key_name in key_map:
                        key_ids.append(key_map[key_name])
                    else:
                        logger.warning(f"Key '{key_name}' not found in key_dictionary")

                logger.info(
                    f"Resolved {len(key_ids)} key IDs: {dict(zip(key_names[: len(key_ids)], key_ids))}"
                )
                return key_ids

        except Exception as e:
            logger.error(f"Error resolving key IDs: {e}")
            return []

    def _get_key_id(self, key_name: str) -> Optional[int]:
        """
        Get single key_id for a key name.

        Args:
            key_name: Key name like 'volt' or 'sensor_00'

        Returns:
            Integer key_id or None if not found
        """
        try:
            with self.engine.connect() as conn:
                query = text(
                    """
                    SELECT key_id
                    FROM key_dictionary
                    WHERE key = :key_name
                """
                )

                result = conn.execute(query, {"key_name": key_name})
                row = result.fetchone()
                return row.key_id if row else None

        except Exception as e:
            logger.error(f"Error getting key_id for '{key_name}': {e}")
            return None

    def fetch_predictive_model_config(self, model_id: str) -> Dict[str, Any]:
        """
        Fetch predictive model configuration from database.

        This method retrieves the predictive model configuration which includes:
        - device_id: The actual device ID associated with this model
        - attributes: Model configuration (telemetry_keys, hyperparameters, etc.)
        - forecast_algorithm: Forecasting algorithm to use
        - anomaly_algorithm: Anomaly detection algorithm to use

        Args:
            model_id: Predictive maintenance configuration ID

        Returns:
            Dictionary with model configuration including 'device_id', 'attributes', etc.

        Raises:
            ValueError: If model_id not found in database
        """
        try:
            with self.engine.connect() as conn:
                query = text(
                    """
                    SELECT 
                        device_id, 
                        attributes,
                        forecast_algorithm,
                        anomaly_algorithm,
                        name,
                        forecast_start_date,
                        forecast_end_date,
                        anomaly_start_date,
                        anomaly_end_date
                    FROM predictive_maintenance_config 
                    WHERE id = :model_id
                """
                )

                result = conn.execute(query, {"model_id": model_id})
                row = result.fetchone()

                if not row:
                    raise ValueError(
                        f"Predictive maintenance configuration not found for model_id: {model_id}"
                    )

                config = {
                    "device_id": str(row.device_id),
                    "attributes": row.attributes if hasattr(row, "attributes") else {},
                    "forecast_algorithm": (
                        row.forecast_algorithm if hasattr(row, "forecast_algorithm") else "ARIMA"
                    ),
                    "anomaly_algorithm": (
                        row.anomaly_algorithm if hasattr(row, "anomaly_algorithm") else "THRESHOLD"
                    ),
                    "name": row.name if hasattr(row, "name") else "Unknown",
                    # forecast_grouping_ms is now stored per-sensor in attributes, with fallback to 5 seconds
                    "forecast_grouping_ms": 5000,
                }

                logger.info(
                    f"Fetched predictive maintenance config for {model_id}: device_id={config['device_id']}, name={config['name']}"
                )
                return config

        except Exception as e:
            logger.error(f"Error fetching predictive maintenance config for {model_id}: {e}")
            raise

    def fetch_model_telemetry_keys(self, model_id: str) -> List[str]:
        """
        Fetch telemetry keys from model configuration.

        Args:
            model_id: Model/Device UUID

        Returns:
            List of telemetry keys configured for this model
        """
        try:
            with self.engine.connect() as conn:
                # Try to fetch from server attributes (model config)
                # First get the key_id for 'telemetry_keys'
                # telemetry_keys_attr_id = self._get_key_id('telemetry_keys')

                # if telemetry_keys_attr_id:
                #     config_query = text(
                #         """
                #         SELECT
                #             str_v as config_value
                #         FROM attribute_kv
                #         WHERE entity_id = :model_id
                #         AND attribute_key = :telemetry_keys_attr_id
                #         LIMIT 1
                #     """
                #     )

                #     result = conn.execute(config_query, {
                #         "model_id": model_id,
                #         "telemetry_keys_attr_id": telemetry_keys_attr_id
                #     })
                #     row = result.fetchone()
                # else:
                #     row = None

                # if row and row.config_value:
                #     # Parse comma-separated list or JSON
                #     import json

                #     try:
                #         # Try JSON first
                #         keys = json.loads(row.config_value)
                #         if isinstance(keys, list):
                #             return keys
                #     except:
                #         # Fall back to comma-separated
                #         return [
                #             k.strip() for k in row.config_value.split(",") if k.strip()
                #         ]

                # # If no config found, discover from actual telemetry data
                # logger.info(
                #     f"No telemetry_keys config found, discovering from ts_kv table"
                # )

                # Simply get all keys from ts_kv for this device
                # (errors/failures/maintenance are in separate tables, not ts_kv)
                discover_query = text(
                    """
                    SELECT DISTINCT ts_kv.key, kd.key as key_name
                    FROM ts_kv
                    JOIN key_dictionary kd ON ts_kv.key = kd.key_id
                    WHERE ts_kv.entity_id = :model_id
                    LIMIT 50
                """
                )

                discover_result = conn.execute(discover_query, {"model_id": model_id})
                discovered_keys = [row.key_name for row in discover_result]

                if discovered_keys:
                    logger.info(f"Discovered telemetry keys: {discovered_keys}")
                    return discovered_keys

                # Fall back to default
                logger.warning(
                    f"No telemetry keys found for {model_id}, using defaults: {self.telemetry_keys}"
                )
                return self.telemetry_keys

        except Exception as e:
            logger.error(f"Error fetching telemetry keys: {e}")
            return self.telemetry_keys

    """
    should return dataframe with columns:
    datetime, volt, rotate, pressure, vibration
    """

    def fetch_telemetry_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            # start_date = datetime.now()
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()
        # cutoff_date = start_date - timedelta(days=days_back)
        cutoff_date = start_date

        # Fetch telemetry keys from model configuration
        telemetry_keys = self.fetch_model_telemetry_keys(device_id)

        # Convert telemetry keys to key IDs
        telemetry_key_ids = self._get_key_ids(telemetry_keys)
        if not telemetry_key_ids:
            return pd.DataFrame(), None

        # Create key_id to key_name mapping for later use
        key_id_to_name = dict(zip(telemetry_key_ids, telemetry_keys))

        with self.engine.connect() as conn:
            # Build dynamic SQL for telemetry key IDs (integers)
            telemetry_keys_sql = ", ".join([str(kid) for kid in telemetry_key_ids])

            # Build query with optional end_date filter
            if end_date is not None:
                telemetry_query = text(
                    f"""
                    SELECT
                        ts,
                        key,
                        COALESCE(dbl_v, long_v, str_v::float) as value
                    FROM ts_kv
                    WHERE entity_id = :device_id
                    AND ts >= :cutoff_ts
                    AND ts <= :end_ts
                    AND key IN ({telemetry_keys_sql})
                    ORDER BY ts
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_ts": int(cutoff_date.timestamp() * 1000),
                    "end_ts": int(end_date.timestamp() * 1000),
                }
            else:
                telemetry_query = text(
                    f"""
                    SELECT
                        ts,
                        key,
                        COALESCE(dbl_v, long_v, str_v::float) as value
                    FROM ts_kv
                    WHERE entity_id = :device_id
                    AND ts >= :cutoff_ts
                    AND key IN ({telemetry_keys_sql})
                    ORDER BY ts
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_ts": int(cutoff_date.timestamp() * 1000),
                }

            telemetry_result = conn.execute(telemetry_query, query_params)

            telemetry_data = []
            for row in telemetry_result:
                telemetry_data.append(
                    {
                        "datetime": datetime.fromtimestamp(row.ts / 1000),
                        "key": key_id_to_name.get(row.key),
                        "value": float(row.value),
                    }
                )

            if len(telemetry_data) > 1:
                # Pivot telemetry data
                telemetry_df = pd.DataFrame(telemetry_data)
                telemetry_pivot = telemetry_df.pivot_table(
                    index="datetime", columns="key", values="value"
                ).reset_index()
                return telemetry_pivot
        return pd.DataFrame(
            {
                "datetime": [],
                # add telemetry_keys as columns
                **{key: [] for key in telemetry_keys},
            }
        )
        # Convert to dataframe
        # with columns datetime, volt, rotate, pressure, vibration
        # join by datetime

    """
    should return dataframe with columns:
    datetime, comp
    """

    def fetch_maintenance_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            # start_date = datetime.now()
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        # cutoff_date = start_date - timedelta(days=days_back)
        cutoff_date = start_date

        # print(f"[FETCH_MAINTENANCE_DATA] fetch data from {cutoff_date} to {end_date}", flush=True)

        with self.engine.connect() as conn:
            if end_date is not None:
                maint_query = text(
                    """
                    SELECT
                        maintenance_date,
                        description,
                        parts_replaced
                    FROM device_maintenance
                    WHERE device_id = :device_id
                    AND maintenance_date >= :cutoff_time
                    AND maintenance_date <= :end_time
                    ORDER BY maintenance_date
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_time": str(cutoff_date),
                    "end_time": str(end_date),
                }
            else:
                maint_query = text(
                    """
                    SELECT
                        maintenance_date,
                        description,
                        parts_replaced
                    FROM device_maintenance
                    WHERE device_id = :device_id
                    AND maintenance_date >= :cutoff_time
                    ORDER BY maintenance_date
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_time": cutoff_date,
                }

            maint_result = conn.execute(maint_query, query_params)

            # print("Fetched maintenance records:", flush=True)
            # print(maint_result.fetchall(), flush=True)

            # replace maintenance_date with datetime
            # and parts_replaced with comp

            maint_data = []
            for row in maint_result:
                maint_data.append(
                    {
                        "datetime": row.maintenance_date,
                        "comp": row.parts_replaced,
                    }
                )

            if len(maint_data) == 0:
                # print(f"Returning empty dataframe", flush=True)
                return pd.DataFrame(
                    {
                        "datetime": [],
                        "comp": [],
                    }
                )

            return pd.DataFrame(maint_data)

    def fetch_error_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            # start_date = datetime.now()
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        # cutoff_date = start_date - timedelta(days=days_back)
        cutoff_date = start_date

        # print(f"[FETCH_ERROR_DATA] fetch error data from {cutoff_date} to {end_date}", flush=True)

        with self.engine.connect() as conn:
            if end_date is not None:
                error_query = text(
                    """
                    SELECT
                        error_time,
                        error_code
                    FROM device_errors
                    WHERE device_id = :device_id
                    AND error_time >= :cutoff_time
                    AND error_time <= :end_time
                    ORDER BY error_time
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_time": str(cutoff_date),
                    "end_time": str(end_date),
                }
            else:
                error_query = text(
                    """
                    SELECT
                        error_time,
                        error_code
                    FROM device_errors
                    WHERE device_id = :device_id
                    AND error_time >= :cutoff_time
                    ORDER BY error_time
                """
                )
                query_params = {
                    "device_id": device_id,
                    "cutoff_time": cutoff_date,
                }

            error_result = conn.execute(error_query, query_params)

            # replace error_time with datetime
            # and error_code with errorID
            error_data = []
            for row in error_result:
                error_data.append(
                    {
                        "datetime": row.error_time,
                        "errorID": row.error_code,
                    }
                )

            if len(error_data) == 0:
                return pd.DataFrame(
                    {
                        "datetime": [],
                        "errorID": [],
                    }
                )

            return pd.DataFrame(error_data)

    def fetch_failure_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            # start_date = datetime.now()
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()
        # cutoff_date = start_date - timedelta(days=days_back)
        cutoff_date = start_date

        # print(
        #     f"[FETCH_FAILURE_DATA] fetch failure data from {cutoff_date} to {end_date}", flush=True
        # )

        with self.engine.connect() as conn:
            failure_query = text(
                """
                SELECT
                    failure_time,
                    root_cause
                FROM device_failures
                WHERE device_id = :device_id
                AND failure_time >= :cutoff_time
                AND failure_time <= :end_time
                ORDER BY failure_time
            """
            )
            query_params = {
                "device_id": device_id,
                "cutoff_time": str(cutoff_date),
                "end_time": str(end_date),
            }

            failure_result = conn.execute(failure_query, query_params)

            # replace failure_time with datetime
            # and root_cause with failureID
            failure_data = []
            for row in failure_result:
                failure_data.append(
                    {
                        "datetime": pd.to_datetime(row.failure_time),
                        "failure": row.root_cause,
                    }
                )

            if len(failure_data) == 0:
                return pd.DataFrame(
                    {
                        "datetime": [],
                        "failure": [],
                    }
                )

            return pd.DataFrame(failure_data)

    """
    should return a dataframe with columns:
    age, model
    """

    def fetch_machines_data(self, device_id: str) -> pd.DataFrame:
        age_key_id = self._get_key_id("age")
        model_key_id = self._get_key_id("model")
        machine_age = 10
        machine_model = "model3"  # default value

        if age_key_id:
            age_query = text(
                """
                    SELECT
                        COALESCE(long_v, dbl_v, str_v::int) as age
                    FROM attribute_kv
                    WHERE entity_id = :device_id
                    AND attribute_key = :age_key_id
                    LIMIT 1
                """
            )

            with self.engine.connect() as conn:
                age_result = conn.execute(
                    age_query, {"device_id": device_id, "age_key_id": age_key_id}
                )
                for row in age_result:
                    machine_age = int(row.age)

        if model_key_id:
            model_query = text(
                """
                    SELECT
                        str_v as model
                    FROM attribute_kv
                    WHERE entity_id = :device_id
                    AND attribute_key = :model_key_id
                    LIMIT 1
                """
            )

            with self.engine.connect() as conn:
                model_result = conn.execute(
                    model_query, {"device_id": device_id, "model_key_id": model_key_id}
                )
                for row in model_result:
                    machine_model = str(row.model)

        return pd.DataFrame({"age": [machine_age], "model": [machine_model]})

    def fetch_anomaly_training_data(
        self,
        device_id: str,
        days_back: int = 90,
        include_failures: bool = True,
        start_date: Optional[datetime] = None,
    ) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
        """
        Fetch training data for anomaly prediction model.

        This method creates features following the notebook pattern:
        - Telemetry aggregations (3h and 24h windows) - DYNAMIC based on model config
        - Error counts (24h rolling window)
        - Component maintenance history
        - Machine age

        Args:
            device_id: Device UUID
            days_back: Number of days of historical data to fetch
            include_failures: Whether to include failure labels

        Returns:
            Tuple of (features_df, labels_series) where:
            - features_df has columns: [key]mean_3h, [key]sd_3h for each telemetry key,
                                       [key]mean_24h, [key]sd_24h for each telemetry key,
                                       error1count, error2count, ...,
                                       comp1, comp2, comp3, comp4, age
            - labels_series contains binary failure labels (0/1) for next 24h
        """
        try:
            if start_date is None:
                start_date = datetime.now()
            cutoff_date = start_date - timedelta(days=days_back)

            # Fetch telemetry keys from model configuration
            telemetry_keys = self.fetch_model_telemetry_keys(device_id)
            logger.info(f"Using telemetry keys for {device_id}: {telemetry_keys}")

            # Convert telemetry keys to key IDs
            telemetry_key_ids = self._get_key_ids(telemetry_keys)
            if not telemetry_key_ids:
                logger.error(f"No valid key IDs found for telemetry keys: {telemetry_keys}")
                return pd.DataFrame(), None

            # Create key_id to key_name mapping for later use
            key_id_to_name = dict(zip(telemetry_key_ids, telemetry_keys))
            logger.info(f"Using telemetry key IDs: {key_id_to_name}")

            with self.engine.connect() as conn:
                # Build dynamic SQL for telemetry key IDs (integers)
                telemetry_keys_sql = ", ".join([str(kid) for kid in telemetry_key_ids])

                # Fetch raw telemetry data (dynamic based on configuration)
                telemetry_query = text(
                    f"""
                    SELECT
                        ts,
                        key,
                        COALESCE(dbl_v, long_v, str_v::float) as value
                    FROM ts_kv
                    WHERE entity_id = :device_id
                    AND ts >= :cutoff_ts
                    AND key IN ({telemetry_keys_sql})
                    ORDER BY ts
                """
                )

                telemetry_result = conn.execute(
                    telemetry_query,
                    {
                        "device_id": device_id,
                        "cutoff_ts": int(cutoff_date.timestamp() * 1000),
                    },
                )

                telemetry_data = []
                for row in telemetry_result:
                    # Map key_id back to key_name
                    key_name = key_id_to_name.get(row.key, f"key_{row.key}")
                    telemetry_data.append(
                        {
                            "datetime": pd.to_datetime(row.ts, unit="ms"),
                            "key": key_name,
                            "value": row.value,
                        }
                    )

                if len(telemetry_data) == 0:
                    logger.warning(f"No telemetry data found for device {device_id}")
                    # print(
                    #     f"[FETCH] No telemetry data found for device {device_id}",
                    #     flush=True,
                    # )
                    return pd.DataFrame(), None

                # print(
                #     f"[FETCH] Got {len(telemetry_data)} telemetry records for device {device_id}",
                #     flush=True,
                # )

                # Pivot telemetry data
                telemetry_df = pd.DataFrame(telemetry_data)
                telemetry_pivot = telemetry_df.pivot_table(
                    index="datetime", columns="key", values="value"
                ).reset_index()

                # print(
                #     f"[FETCH] After pivot: {telemetry_pivot.shape}, columns: {list(telemetry_pivot.columns)}",
                #     flush=True,
                # )

                # Resample to 3-hour intervals
                telemetry_pivot.set_index("datetime", inplace=True)
                telemetry_3h = telemetry_pivot.resample("3h").agg(["mean", "std"]).reset_index()

                # print(f"[FETCH] After 3h resample: {telemetry_3h.shape}", flush=True)

                # Flatten column names
                telemetry_3h.columns = [
                    "datetime" if col[0] == "datetime" else f"{col[0]}{col[1]}_3h"
                    for col in telemetry_3h.columns
                ]

                # Calculate 24-hour rolling features on the 3h resampled data
                # Need to work with the 3h data before flattening column names
                telemetry_3h_temp = telemetry_pivot.resample("3h").agg(["mean", "std"])
                telemetry_24h_list = []

                for col in telemetry_keys:  # Dynamic telemetry keys
                    if (col, "mean") in telemetry_3h_temp.columns:
                        mean_col = (col, "mean")
                        # Apply 24h rolling window (8 periods of 3h each)
                        rolling_mean = (
                            telemetry_3h_temp[mean_col].rolling(window=8, center=False).mean()
                        )
                        rolling_std = (
                            telemetry_3h_temp[mean_col].rolling(window=8, center=False).std()
                        )
                        telemetry_24h_list.append(rolling_mean.rename(f"{col}mean_24h"))
                        telemetry_24h_list.append(rolling_std.rename(f"{col}sd_24h"))

                # Concatenate 24h rolling features
                if telemetry_24h_list:
                    telemetry_24h = pd.concat(telemetry_24h_list, axis=1).reset_index()
                else:
                    telemetry_24h = telemetry_3h_temp.reset_index()[["datetime"]]

                # print(
                #     f"[FETCH] 24h features shape before dropna: {telemetry_24h.shape}",
                #     flush=True,
                # )

                # Merge 3h and 24h features (both on same 3h resampled datetime index)
                # print(
                #     f"[FETCH] telemetry_3h shape: {telemetry_3h.shape}, telemetry_24h shape: {telemetry_24h.shape}",
                #     flush=True,
                # )
                features_df = telemetry_3h.merge(telemetry_24h, on="datetime", how="left")
                # print(
                #     f"[FETCH] After merge, features_df shape: {features_df.shape}",
                #     flush=True,
                # )

                # Drop rows where ALL 24h features are NaN (first ~8 periods)
                feature_cols_24h = [col for col in features_df.columns if "24h" in col]
                if feature_cols_24h:
                    # print(
                    #     f"[FETCH] Before dropna on 24h features: {len(features_df)} rows",
                    #     flush=True,
                    # )
                    features_df = features_df.dropna(subset=feature_cols_24h, how="all")
                    # print(
                    #     f"[FETCH] After dropna on 24h features: {len(features_df)} rows",
                    #     flush=True,
                    # )

                # Fetch error counts (24h rolling window)
                # Query from device_errors table instead of ts_kv
                error_query = text(
                    """
                    SELECT
                        error_time,
                        error_code,
                        1 as value
                    FROM device_errors
                    WHERE device_id = :device_id
                    AND error_time >= :cutoff_time
                    ORDER BY error_time
                """
                )

                error_result = conn.execute(
                    error_query,
                    {
                        "device_id": device_id,
                        "cutoff_time": cutoff_date,
                    },
                )

                error_data = []
                for row in error_result:
                    error_data.append(
                        {
                            "datetime": pd.to_datetime(row.error_time),
                            "errorID": row.error_code,
                            "value": 1,  # Each row represents one error occurrence
                        }
                    )

                if error_data:
                    error_df = pd.DataFrame(error_data)
                    error_pivot = error_df.pivot_table(
                        index="datetime",
                        columns="errorID",
                        values="value",
                        fill_value=0,
                    )

                    # 24h rolling sum for error counts
                    error_24h = error_pivot.rolling(window="24h").sum().reset_index()
                    error_24h.columns = ["datetime"] + [
                        f"{col}count" for col in error_pivot.columns
                    ]

                    # Merge with features
                    features_df = features_df.merge(error_24h, on="datetime", how="left")

                    # Fill missing error counts with 0
                    for i in range(1, 6):
                        col = f"error{i}count"
                        if col not in features_df.columns:
                            features_df[col] = 0
                        else:
                            features_df[col] = features_df[col].fillna(0)
                else:
                    # No error data, create zero columns
                    for i in range(1, 6):
                        features_df[f"error{i}count"] = 0

                # Fetch component maintenance history from device_maintenance table
                maint_query = text(
                    """
                    SELECT
                        maintenance_date,
                        description,
                        parts_replaced
                    FROM device_maintenance
                    WHERE device_id = :device_id
                    AND maintenance_date >= :cutoff_time
                    ORDER BY maintenance_date
                """
                )

                maint_result = conn.execute(
                    maint_query,
                    {
                        "device_id": device_id,
                        "cutoff_time": cutoff_date,
                    },
                )

                maint_data = []
                for row in maint_result:
                    # Try to extract component from description first (e.g., "Maintenance of comp2")
                    comp = row.parts_replaced

                    if comp:
                        maint_data.append(
                            {
                                "datetime": pd.to_datetime(row.maintenance_date),
                                "comp": comp,
                            }
                        )

                # Use notebook's merge strategy for maintenance data
                if maint_data:
                    # Create maintenance DataFrame with one-hot encoding
                    maint_df = pd.DataFrame(maint_data)

                    # One-hot encode components
                    comp_rep = pd.get_dummies(
                        maint_df.set_index("datetime"), columns=["comp"]
                    ).reset_index()

                    # Rename columns to match notebook pattern
                    comp_rep.columns = ["datetime"] + [
                        col.replace("comp_", "") for col in comp_rep.columns if col != "datetime"
                    ]

                    # Merge with telemetry grid to get all timestamps
                    telemetry_grid = features_df[["datetime"]].copy()
                    comp_rep = (
                        telemetry_grid.merge(comp_rep, on="datetime", how="outer")
                        .fillna(0)
                        .sort_values(by="datetime")
                    )

                    # Forward-fill maintenance dates (notebook pattern)
                    components = ["comp1", "comp2", "comp3", "comp4"]
                    for comp in components:
                        if comp not in comp_rep.columns:
                            comp_rep[comp] = 0

                        # Convert to datetime where maintenance occurred
                        # Fix pandas FutureWarning by using pd.NA instead of None
                        comp_rep[comp] = comp_rep[comp].astype(object)
                        comp_rep.loc[comp_rep[comp] < 1, comp] = pd.NA
                        comp_rep.loc[comp_rep[comp].notna(), comp] = comp_rep.loc[
                            comp_rep[comp].notna(), "datetime"
                        ]
                        comp_rep[comp] = comp_rep[comp].ffill()

                        # Calculate days since maintenance
                        comp_rep[comp] = (
                            comp_rep["datetime"] - pd.to_datetime(comp_rep[comp])
                        ) / np.timedelta64(1, "D")
                        comp_rep[comp] = comp_rep[comp].fillna(
                            365
                        )  # Default if no maintenance history

                    # Merge with features_df
                    features_df = features_df.merge(
                        comp_rep[["datetime"] + components], on="datetime", how="left"
                    )

                    # Fill any remaining NaN values with 365
                    for comp in components:
                        features_df[comp] = features_df[comp].fillna(365)
                else:
                    # No maintenance data - set default values
                    for i in range(1, 5):
                        features_df[f"comp{i}"] = 365

                # print(
                #     f"[FETCH] Before adding age, features_df shape: {features_df.shape}",
                #     flush=True,
                # )

                # Add machine age (fetch from device attributes)
                age_key_id = self._get_key_id("age")
                machine_age = 10  # Default age

                if age_key_id:
                    age_query = text(
                        """
                        SELECT
                            COALESCE(long_v, dbl_v, str_v::int) as age
                        FROM attribute_kv
                        WHERE entity_id = :device_id
                        AND attribute_key = :age_key_id
                        LIMIT 1
                    """
                    )

                    age_result = conn.execute(
                        age_query, {"device_id": device_id, "age_key_id": age_key_id}
                    )
                    age_row = age_result.fetchone()
                    machine_age = age_row.age if age_row else 10

                features_df["age"] = machine_age

                # Fetch failure labels if requested from device_failures table
                labels = None
                if include_failures:
                    failure_query = text(
                        """
                        SELECT
                            failure_time,
                            root_cause
                        FROM device_failures
                        WHERE device_id = :device_id
                        AND failure_time >= :cutoff_time
                        ORDER BY failure_time
                    """
                    )

                    failure_result = conn.execute(
                        failure_query,
                        {
                            "device_id": device_id,
                            "cutoff_time": cutoff_date,
                        },
                    )

                    failure_data = []
                    for row in failure_result:
                        # Floor failure time to nearest 3-hour interval to match feature timestamps
                        failure_dt = pd.to_datetime(row.failure_time)
                        failure_dt_floored = failure_dt.floor("3H")
                        failure_data.append(
                            {
                                "datetime": failure_dt_floored,
                                "failure_component": (row.root_cause if row.root_cause else "none"),
                            }
                        )

                    if failure_data:
                        failure_df = pd.DataFrame(failure_data)
                        # print(
                        #     f"[FETCH] Found {len(failure_df)} failure records",
                        #     flush=True,
                        # )
                        # print(
                        #     f"[FETCH] Failure timestamps (floored to 3h): {failure_df['datetime'].tolist()[:5]}",
                        #     flush=True,
                        # )
                        # print(
                        #     f"[FETCH] Feature datetime range: {features_df['datetime'].min()} to {features_df['datetime'].max()}",
                        #     flush=True,
                        # )

                        features_with_labels = features_df.merge(
                            failure_df, on="datetime", how="left"
                        )
                        labels = features_with_labels["failure_component"].fillna("none")
                        # print(
                        #     f"[FETCH] Labels value counts: {labels.value_counts().to_dict()}",
                        #     flush=True,
                        # )

                        features_df = features_with_labels.drop("failure_component", axis=1)
                    else:
                        # print(
                        #     f"[FETCH] No failure data found for device {device_id}",
                        #     flush=True,
                        # )
                        pass

                # Drop datetime column for training
                if "datetime" in features_df.columns:
                    features_df = features_df.drop("datetime", axis=1)

                # Build expected columns dynamically based on telemetry keys
                expected_cols = []

                # Add telemetry features (3h and 24h)
                for key in telemetry_keys:
                    expected_cols.extend(
                        [
                            f"{key}mean_3h",
                            f"{key}sd_3h",
                            f"{key}mean_24h",
                            f"{key}sd_24h",
                        ]
                    )

                # Add error counts
                for i in range(1, len(self.error_keys) + 1):
                    expected_cols.append(f"error{i}count")

                # Add component features
                expected_cols.extend(self.component_keys)

                # Add age
                expected_cols.append("age")

                # Ensure all expected columns are present
                for col in expected_cols:
                    if col not in features_df.columns:
                        features_df[col] = 0

                # Reorder columns
                features_df = features_df[expected_cols]

                logger.info(
                    f"Fetched {len(features_df)} samples with {len(expected_cols)} features: {expected_cols}"
                )
                # print(
                #     f"[FETCH] Returning features_df with {len(features_df)} samples and labels: {type(labels)}",
                #     flush=True,
                # )
                return features_df, labels

        except Exception as e:
            logger.error(f"Error fetching anomaly training data: {e}")
            import traceback

            # print(f"[FETCH ERROR] Exception occurred: {str(e)}", flush=True)
            traceback.print_exc()
            return pd.DataFrame(), None

    def fetch_forecast_training_data(
        self,
        device_id: str,
        sensor_key: str = "sensor_00",
        days_back: int = 90,
        end_date: Optional[datetime] = None,
        start_date: Optional[datetime] = None,
        limit: int = 10000,
        desc: bool = False,
    ) -> pd.DataFrame:
        """
        Fetch training data for time series forecasting.

        Args:
            device_id: ThingsBoard device UUID
            sensor_key: Sensor name/key to forecast
            days_back: Number of days of historical data to fetch
            end_date: Optional end date (defaults to now)
            start_date: Optional start date (overrides days_back if provided)

        Returns:
            DataFrame with 'ds' (timestamp) and 'y' (value) columns (Prophet format)
        """
        logger.info(
            f"Fetching forecast data for device {device_id}, sensor {sensor_key} ({days_back} days)"
        )

        try:
            # Calculate time range
            end_time = end_date or datetime.now()
            start_time = start_date or (end_time - timedelta(days=days_back))

            # Fetch time series data
            forecast_df = self._fetch_time_series_data(
                device_id=device_id,
                sensor_key=sensor_key,
                limit=limit,
                desc=desc,
                start_date=start_time,
                end_date=end_time,
            )

            if forecast_df.empty:
                return forecast_df

            return forecast_df

        except Exception as e:
            raise

    def fetch_device_sensors(self, device_id: str) -> List[str]:
        """
        Fetch list of available sensors for a device.

        Args:
            device_id: ThingsBoard device UUID

        Returns:
            List of sensor keys
        """
        logger.info(f"Fetching available sensors for device {device_id}")

        try:
            query = text(
                """
                SELECT DISTINCT key
                FROM ts_kv
                WHERE entity_id = :device_id
                ORDER BY key
            """
            )

            with self.engine.connect() as conn:
                result = conn.execute(query, {"device_id": device_id})
                sensors = [row[0] for row in result]

            logger.info(f"Found {len(sensors)} sensors for device {device_id}")
            return sensors

        except Exception as e:
            logger.error(f"Error fetching device sensors: {e}")
            raise

    def fetch_all_devices(self) -> List[Dict[str, str]]:
        """
        Fetch list of all devices in the system.

        Returns:
            List of dictionaries with device info (id, name, type)
        """
        logger.info("Fetching all devices")

        try:
            query = text(
                """
                SELECT id, name, type
                FROM device
                WHERE search_text IS NOT NULL
                ORDER BY name
            """
            )

            with self.engine.connect() as conn:
                result = conn.execute(query)
                devices = [{"id": row[0], "name": row[1], "type": row[2]} for row in result]

            logger.info(f"Found {len(devices)} devices")
            return devices

        except Exception as e:
            logger.error(f"Error fetching devices: {e}")
            raise

    # ==================== Private Helper Methods ====================

    def fetch_sensor_data(
        self,
        sensor_key: str,
        device_id: Optional[str] = None,
        limit: int = 1000,
        start_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """
        Fetch all time series data for a given sensor key across all devices.

        Args:
            sensor_key: Sensor name/key to fetch
        Returns:
            DataFrame with columns: datetime, value
        """
        logger.info(f"Fetching all data for sensor key '{sensor_key}'")

        try:
            sensor_key_id = self._get_key_id(sensor_key)
            if not sensor_key_id:
                logger.error(f"Sensor key '{sensor_key}' not found in key_dictionary")
                return pd.DataFrame(columns=["datetime", "value"])
            query = text(
                """
                SELECT
                    ts as datetime,
                    COALESCE(dbl_v, long_v, str_v::float) as value
                FROM ts_kv
                WHERE key = :sensor_key_id
                ORDER BY ts DESC
                LIMIT :limit
            """
            )
            params = {"sensor_key_id": sensor_key_id, "limit": limit}
            with self.engine.connect() as conn:
                result = conn.execute(query, params)
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
                df.rename(columns={"value": sensor_key}, inplace=True)
                df = df.sort_values("datetime").reset_index(drop=True)
                return df

            return pd.DataFrame(columns=["datetime", sensor_key])

        except Exception as e:
            logger.error(f"Error fetching sensor data: {e}")
            return pd.DataFrame(columns=["datetime", "value"])

    def _fetch_failure_labels(
        self, device_id: str, start_ts: int, end_ts: int, index: pd.Index
    ) -> pd.Series:
        """
        Fetch failure labels for anomaly detection.

        Returns Series with binary failure labels (0 or 1).
        """
        query = text(
            """
            SELECT 
                ts,
                CASE 
                    WHEN bool_v = true THEN 1
                    WHEN str_v = 'true' THEN 1
                    WHEN long_v = 1 THEN 1
                    ELSE 0
                END as failure
            FROM ts_kv
            WHERE entity_id = :device_id
                AND ts BETWEEN :start_ts AND :end_ts
                AND key = 'failure_within_24h'
            ORDER BY ts
        """
        )

        with self.engine.connect() as conn:
            result = conn.execute(
                query, {"device_id": device_id, "start_ts": start_ts, "end_ts": end_ts}
            )

            failures = []
            for row in result:
                failures.append({"timestamp": pd.to_datetime(row[0], unit="ms"), "failure": row[1]})

        if len(failures) == 0:
            # No failure data found, create synthetic labels
            logger.warning("No failure labels found, creating synthetic labels")
            return pd.Series(np.zeros(len(index)), index=index, name="failure_within_24h")

        # Align with features index
        failure_df = pd.DataFrame(failures).set_index("timestamp")

        # Resample to match features frequency
        failure_series = failure_df["failure"].reindex(index, method="ffill", fill_value=0)
        failure_series.name = "failure_within_24h"

        return failure_series

    def _fetch_time_series_data(
        self,
        device_id: str,
        sensor_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = None,
        desc: bool = True,
        group_by: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch time series data for forecasting.

        Returns DataFrame with 'ds' (timestamp) and 'y' (value) columns.
        """
        # Convert sensor_key to key_id
        sensor_key_id = self._get_key_id(sensor_key)

        if not sensor_key_id:
            logger.error(f"Sensor key '{sensor_key}' not found in key_dictionary")
            return pd.DataFrame(columns=["ds", "y"])

        if start_date is None:
            start_date = datetime(1970, 1, 1)

        if end_date is None:
            end_date = datetime.now()

        order_clause = "DESC" if desc else "ASC"
        limit_clause = " LIMIT :limit" if limit is not None else ""

        text_q = f"""
            SELECT
                ts as datetime,
                COALESCE(dbl_v, long_v, str_v::float) as value
            FROM ts_kv
            WHERE entity_id = :device_id
                AND ts BETWEEN :start_ts AND :end_ts
                AND key = :sensor_key_id
            ORDER BY ts {order_clause}
            {limit_clause}
            """

        query = text(text_q)
        # Build parameters dictionary, only including limit if it's not None
        params = {
            "device_id": device_id,
            "start_ts": int(start_date.timestamp() * 1000),
            "end_ts": int(end_date.timestamp() * 1000),
            "sensor_key_id": sensor_key_id,
        }
        if limit is not None:
            params["limit"] = limit

        with self.engine.connect() as conn:
            result = conn.execute(query, params)

            # convert result to dataframe with datetime to pd.datetime
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
            df.rename(columns={"value": sensor_key}, inplace=True)

            df = df.drop_duplicates(subset=["datetime"], keep="last")
            df = df.sort_values("datetime").reset_index(drop=True)

            return df

        return pd.DataFrame(columns=["datetime", sensor_key])

    def test_connection(self) -> bool:
        """
        Test if database connection is working.

        Returns:
            True if connection is successful, False otherwise
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __repr__(self) -> str:
        db_name = self.database_url.split("/")[-1].split("?")[0]
        return f"DataRegistry(database='{db_name}')"
