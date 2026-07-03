from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from tb_ce_client import EntityId

from src.logger import logger
from src.model.client import get_client


class DataRegistry:
    def __init__(
        self,
        database_url: str,
        telemetry_keys: List[str] | None = None,
        error_keys: List[str] | None = None,
        component_keys: List[str] | None = None,
    ):
        self.database_url = database_url
        self.engine: Optional[Engine] = None

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

        self.telemetry_keys_ids = self._get_key_ids(self.telemetry_keys)

    def _connect(self) -> None:
        try:
            self.engine = create_engine(self.database_url, echo=False)
        except Exception as e:
            raise

    def _get_key_ids(self, key_names: List[str]) -> List[int]:
        if not key_names:
            return []

        try:
            with self.engine.connect() as conn:
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
                    "forecast_grouping_ms": 5000,
                }

                logger.info(
                    "Fetched predictive maintenance config for %s: device_id=%s, name=%s",
                    model_id,
                    config["device_id"],
                    config["name"],
                )
                return config

        except Exception as e:
            logger.error(f"Error fetching predictive maintenance config for {model_id}: {e}")
            raise

    def fetch_model_telemetry_keys(self, model_id: str) -> List[str]:
        try:
            with self.engine.connect() as conn:
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

                logger.warning(
                    f"No telemetry keys found for {model_id}, using defaults: {self.telemetry_keys}"
                )
                return self.telemetry_keys

        except Exception as e:
            logger.error(f"Error fetching telemetry keys: {e}")
            return self.telemetry_keys

    def fetch_telemetry_data(
        self, device_id: str, start_date=None, end_date=None, **kwargs
    ) -> pd.DataFrame:
        start_ts = int(start_date.timestamp() * 1000) if start_date else 0
        end_ts = (
            int(end_date.timestamp() * 1000) if end_date else int(datetime.now().timestamp() * 1000)
        )

        client = get_client()
        keys = client.get_timeseries_keys(entity_type="DEVICE", entity_id=device_id)
        if not keys:
            return pd.DataFrame()

        result = client.get_timeseries_history(
            entity_type="DEVICE",
            entity_id=device_id,
            start_ts=start_ts,
            end_ts=end_ts,
            keys=",".join(keys),
            agg="NONE",
            order_by="ASC",
            limit=str(1_000_000),
        )

        rows = [
            {"datetime": pd.to_datetime(p.ts, unit="ms"), "key": key, "value": float(p.value)}
            for key, points in result.items()
            for p in points
            if p.ts is not None and p.value is not None
        ]
        if not rows:
            return pd.DataFrame()

        return (
            pd.DataFrame(rows)
            .pivot_table(index="datetime", columns="key", values="value")
            .reset_index()
        )

    def fetch_maintenance_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        cutoff_date = start_date

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

            maint_data = []
            for row in maint_result:
                maint_data.append(
                    {
                        "datetime": row.maintenance_date,
                        "comp": row.parts_replaced,
                    }
                )

            if len(maint_data) == 0:
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
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        cutoff_date = start_date

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
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()
        cutoff_date = start_date

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

    def fetch_machines_data(self, device_id: str) -> pd.DataFrame:
        age_key_id = self._get_key_id("age")
        model_key_id = self._get_key_id("model")
        machine_age = 10
        machine_model = "model3"

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
        try:
            if start_date is None:
                start_date = datetime.now()
            cutoff_date = start_date - timedelta(days=days_back)

            telemetry_keys = self.fetch_model_telemetry_keys(device_id)
            logger.info(f"Using telemetry keys for {device_id}: {telemetry_keys}")

            telemetry_key_ids = self._get_key_ids(telemetry_keys)
            if not telemetry_key_ids:
                logger.error(f"No valid key IDs found for telemetry keys: {telemetry_keys}")
                return pd.DataFrame(), None

            key_id_to_name = dict(zip(telemetry_key_ids, telemetry_keys))
            logger.info(f"Using telemetry key IDs: {key_id_to_name}")

            with self.engine.connect() as conn:
                telemetry_keys_sql = ", ".join([str(kid) for kid in telemetry_key_ids])

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
                    return pd.DataFrame(), None

                telemetry_df = pd.DataFrame(telemetry_data)
                telemetry_pivot = telemetry_df.pivot_table(
                    index="datetime", columns="key", values="value"
                ).reset_index()

                telemetry_pivot.set_index("datetime", inplace=True)
                telemetry_3h = telemetry_pivot.resample("3h").agg(["mean", "std"]).reset_index()

                telemetry_3h.columns = [
                    "datetime" if col[0] == "datetime" else f"{col[0]}{col[1]}_3h"
                    for col in telemetry_3h.columns
                ]

                telemetry_3h_temp = telemetry_pivot.resample("3h").agg(["mean", "std"])
                telemetry_24h_list = []

                for col in telemetry_keys:
                    if (col, "mean") in telemetry_3h_temp.columns:
                        mean_col = (col, "mean")
                        rolling_mean = (
                            telemetry_3h_temp[mean_col].rolling(window=8, center=False).mean()
                        )
                        rolling_std = (
                            telemetry_3h_temp[mean_col].rolling(window=8, center=False).std()
                        )
                        telemetry_24h_list.append(rolling_mean.rename(f"{col}mean_24h"))
                        telemetry_24h_list.append(rolling_std.rename(f"{col}sd_24h"))

                if telemetry_24h_list:
                    telemetry_24h = pd.concat(telemetry_24h_list, axis=1).reset_index()
                else:
                    telemetry_24h = telemetry_3h_temp.reset_index()[["datetime"]]

                features_df = telemetry_3h.merge(telemetry_24h, on="datetime", how="left")

                feature_cols_24h = [col for col in features_df.columns if "24h" in col]
                if feature_cols_24h:
                    features_df = features_df.dropna(subset=feature_cols_24h, how="all")
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
                            "value": 1,
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

                    error_24h = error_pivot.rolling(window="24h").sum().reset_index()
                    error_24h.columns = ["datetime"] + [
                        f"{col}count" for col in error_pivot.columns
                    ]

                    features_df = features_df.merge(error_24h, on="datetime", how="left")

                    for i in range(1, 6):
                        col = f"error{i}count"
                        if col not in features_df.columns:
                            features_df[col] = 0
                        else:
                            features_df[col] = features_df[col].fillna(0)
                else:
                    for i in range(1, 6):
                        features_df[f"error{i}count"] = 0
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
                    comp = row.parts_replaced

                    if comp:
                        maint_data.append(
                            {
                                "datetime": pd.to_datetime(row.maintenance_date),
                                "comp": comp,
                            }
                        )

                if maint_data:
                    maint_df = pd.DataFrame(maint_data)

                    comp_rep = pd.get_dummies(
                        maint_df.set_index("datetime"), columns=["comp"]
                    ).reset_index()

                    comp_rep.columns = ["datetime"] + [
                        col.replace("comp_", "") for col in comp_rep.columns if col != "datetime"
                    ]

                    telemetry_grid = features_df[["datetime"]].copy()
                    comp_rep = (
                        telemetry_grid.merge(comp_rep, on="datetime", how="outer")
                        .fillna(0)
                        .sort_values(by="datetime")
                    )

                    components = ["comp1", "comp2", "comp3", "comp4"]
                    for comp in components:
                        if comp not in comp_rep.columns:
                            comp_rep[comp] = 0

                        comp_rep[comp] = comp_rep[comp].astype(object)
                        comp_rep.loc[comp_rep[comp] < 1, comp] = pd.NA
                        comp_rep.loc[comp_rep[comp].notna(), comp] = comp_rep.loc[
                            comp_rep[comp].notna(), "datetime"
                        ]
                        comp_rep[comp] = comp_rep[comp].ffill()

                        comp_rep[comp] = (
                            comp_rep["datetime"] - pd.to_datetime(comp_rep[comp])
                        ) / np.timedelta64(1, "D")
                        comp_rep[comp] = comp_rep[comp].fillna(365)
                    features_df = features_df.merge(
                        comp_rep[["datetime"] + components], on="datetime", how="left"
                    )

                    for comp in components:
                        features_df[comp] = features_df[comp].fillna(365)
                else:
                    for i in range(1, 5):
                        features_df[f"comp{i}"] = 365

                age_key_id = self._get_key_id("age")
                machine_age = 10

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

                        features_with_labels = features_df.merge(
                            failure_df, on="datetime", how="left"
                        )
                        labels = features_with_labels["failure_component"].fillna("none")

                        features_df = features_with_labels.drop("failure_component", axis=1)
                    else:
                        pass

                if "datetime" in features_df.columns:
                    features_df = features_df.drop("datetime", axis=1)

                expected_cols = []

                for key in telemetry_keys:
                    expected_cols.extend(
                        [
                            f"{key}mean_3h",
                            f"{key}sd_3h",
                            f"{key}mean_24h",
                            f"{key}sd_24h",
                        ]
                    )

                for i in range(1, len(self.error_keys) + 1):
                    expected_cols.append(f"error{i}count")

                expected_cols.extend(self.component_keys)

                expected_cols.append("age")

                for col in expected_cols:
                    if col not in features_df.columns:
                        features_df[col] = 0

                features_df = features_df[expected_cols]

                logger.info(
                    f"Fetched {len(features_df)} samples with {len(expected_cols)} features: {expected_cols}"
                )
                return features_df, labels

        except Exception as e:
            logger.error(f"Error fetching anomaly training data: {e}")
            import traceback

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
            forecast_df = self.api_fetch_time_series_data(
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

    def api_fetch_time_series_data(
        self,
        device_id: str,
        sensor_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int | None = None,
        desc: bool = True,
        group_by: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch time series data via ThingsBoard API, DB-fetch-compatible schema."""
        if sensor_key is None:
            logger.error("Sensor key is required for fetching time series data")
            return pd.DataFrame(columns=["datetime", sensor_key])

        start_date = start_date or datetime(1970, 1, 1)
        end_date = end_date or datetime.now()

        ts = get_client().get_timeseries_history(
            entity_type="DEVICE",
            entity_id=device_id,
            start_ts=int(start_date.timestamp() * 1000),
            end_ts=int(end_date.timestamp() * 1000),
            order_by="DESC" if desc else "ASC",
            limit=str(
                limit or 200_000
            ),  # ponytail: TB API defaults to 100 if omitted; 200k mirrors DB path's "unbounded"
            keys=sensor_key,
        )
        records = ts.get(sensor_key, [])
        logger.info(
            f"Fetched {len(records)} rows from ThingsBoard API for device {device_id}, sensor {sensor_key}"
        )

        if not records:
            return pd.DataFrame(columns=["datetime", sensor_key])

        def _row(record):
            if isinstance(record, dict):
                return record.get("ts"), float(record.get("value", 0))
            return record.ts, float(record.value)

        tss, values = zip(*(_row(r) for r in records))
        df = pd.DataFrame({"datetime": pd.to_datetime(tss, unit="ms"), sensor_key: values})
        return (
            df.drop_duplicates(subset=["datetime"], keep="last")
            .sort_values("datetime")
            .reset_index(drop=True)
        )

    def fetch_device_sensors(self, device_id: str) -> List[str]:
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

    def fetch_sensor_data(
        self,
        sensor_key: str,
        device_id: Optional[str] = None,
        limit: int = 1000,
        start_date: Optional[datetime] = None,
    ) -> pd.DataFrame:
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

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def close(self) -> None:
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        db_name = self.database_url.split("/")[-1].split("?")[0]
        return f"DataRegistry(database='{db_name}')"
