from datetime import datetime, timedelta
from functools import reduce
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.logger import logger
from src.model.client import get_client
from src.model.quarkus_client import get_quarkus_client


class DataRegistry:
    def __init__(
        self,
        telemetry_keys: List[str] | None = None,
        error_keys: List[str] | None = None,
        component_keys: List[str] | None = None,
        **_: Any,
    ):
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

        self.telemetry_keys_ids = self._get_key_ids(self.telemetry_keys)

    def _get_key_ids(self, key_names: List[str]) -> List[int]:
        return list(range(len(key_names or [])))

    def _get_key_id(self, key_name: str) -> Optional[int]:
        return None

    def _start_ts(self, start_date: datetime | None) -> int | None:
        return int(start_date.timestamp() * 1000) if start_date else None

    def _end_ts(self, end_date: datetime | None) -> int | None:
        return int(end_date.timestamp() * 1000) if end_date else None

    def _model_id(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            return value.get("id") or value.get("entityId") or value.get("value")
        return getattr(value, "id", None) or str(value)

    def _record_datetime(self, record: dict[str, Any]) -> Any:
        return record.get("datetime") or record.get("dateTime")

    def _naive_datetime(self, value: Any) -> pd.Timestamp:
        timestamp = pd.to_datetime(value)
        if timestamp.tzinfo is not None:
            return timestamp.tz_convert(None)
        return timestamp

    def _get_device_attribute(self, device_id: str, key: str) -> Any:
        client = get_client()
        attempts = [
            lambda: client.get_attributes_by_scope(
                entity_type="DEVICE", entity_id=device_id, scope="SERVER_SCOPE", keys=key
            ),
            lambda: client.get_attributes(
                entity_type="DEVICE", entity_id=device_id, scope="SERVER_SCOPE", keys=key
            ),
            lambda: client.get_attributes(
                entity_type="DEVICE", entity_id=device_id, keys=key
            ),
        ]
        for attempt in attempts:
            try:
                attributes = attempt()
                if isinstance(attributes, dict):
                    return attributes.get(key)
                for attr in attributes or []:
                    attr_key = (
                        attr.get("key") if isinstance(attr, dict) else getattr(attr, "key", None)
                    )
                    if attr_key == key:
                        return (
                            attr.get("value")
                            if isinstance(attr, dict)
                            else getattr(attr, "value", None)
                        )
            except AttributeError:
                continue
            except Exception as exc:
                logger.warning(
                    "Could not fetch ThingsBoard attribute %s for %s: %s",
                    key,
                    device_id,
                    exc,
                )
                break
        return None

    def fetch_predictive_model_config(self, model_id: str) -> Dict[str, Any]:
        try:
            forecast = get_quarkus_client().get_forecast(model_id)
            if not forecast:
                raise ValueError(
                    f"Predictive maintenance configuration not found for model_id: {model_id}"
                )

            config = {
                "device_id": self._model_id(forecast.get("deviceId")),
                "attributes": forecast.get("attributes") or {},
                "forecast_algorithm": forecast.get("forecastAlgorithm") or "ARIMA",
                "anomaly_algorithm": forecast.get("anomalyAlgorithm") or "THRESHOLD",
                "name": forecast.get("name") or "Unknown",
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
            discovered_keys = get_client().get_timeseries_keys(
                entity_type="DEVICE", entity_id=model_id
            )
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
        keys = get_client().get_timeseries_keys(entity_type="DEVICE", entity_id=device_id)
        if not keys:
            return pd.DataFrame()

        return self.api_fetch_time_series_data(
            device_id, keys, start_date=start_date, end_date=end_date, desc=False
        )

    def fetch_maintenance_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        history = get_quarkus_client().get_failure_mode_history(
            device_id,
            start_ts=self._start_ts(start_date),
            end_ts=self._end_ts(end_date),
        )
        maint_data = [
            {
                "datetime": self._naive_datetime(self._record_datetime(row)),
                "comp": row.get("parts_replaced"),
            }
            for row in history.get("maintenance", [])
        ]

        if len(maint_data) == 0:
            return pd.DataFrame({"datetime": [], "comp": []})

        return pd.DataFrame(maint_data).sort_values("datetime").reset_index(drop=True)

    def fetch_error_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()

        history = get_quarkus_client().get_failure_mode_history(
            device_id,
            start_ts=self._start_ts(start_date),
            end_ts=self._end_ts(end_date),
        )
        error_data = [
            {
                "datetime": self._naive_datetime(self._record_datetime(row)),
                "errorID": row.get("error_code"),
            }
            for row in history.get("errors", [])
        ]

        if len(error_data) == 0:
            return pd.DataFrame({"datetime": [], "errorID": []})

        return pd.DataFrame(error_data).sort_values("datetime").reset_index(drop=True)

    def fetch_failure_data(
        self, device_id: str, start_date: datetime = None, end_date: datetime = None, **kwargs
    ) -> pd.DataFrame:
        if start_date is None:
            start_date = datetime(1, 1, 1, 0, 0)
        if end_date is None:
            end_date = datetime.now()
        history = get_quarkus_client().get_failure_mode_history(
            device_id,
            start_ts=self._start_ts(start_date),
            end_ts=self._end_ts(end_date),
        )
        failure_data = [
            {
                "datetime": self._naive_datetime(self._record_datetime(row)),
                "failure": row.get("root_cause"),
            }
            for row in history.get("failures", [])
        ]

        if len(failure_data) == 0:
            return pd.DataFrame({"datetime": [], "failure": []})

        return pd.DataFrame(failure_data).sort_values("datetime").reset_index(drop=True)

    def fetch_machines_data(self, device_id: str) -> pd.DataFrame:
        machine_age = 10
        machine_model = "model3"

        age = self._get_device_attribute(device_id, "age")
        model = self._get_device_attribute(device_id, "model")
        if age is not None:
            machine_age = int(age)
        if model is not None:
            machine_model = str(model)

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

            telemetry_pivot = self.api_fetch_time_series_data(
                device_id, telemetry_keys, start_date=cutoff_date, desc=False
            )
            if telemetry_pivot.empty:
                logger.warning(f"No telemetry data found for device {device_id}")
                return pd.DataFrame(), None

            telemetry_pivot = telemetry_pivot.set_index("datetime")

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
                    rolling_std = telemetry_3h_temp[mean_col].rolling(window=8, center=False).std()
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

            error_df = self.fetch_error_data(device_id, start_date=cutoff_date)
            if not error_df.empty:
                error_df = error_df.assign(
                    datetime=pd.to_datetime(error_df["datetime"]),
                    value=1,
                )
                error_pivot = error_df.pivot_table(
                    index="datetime",
                    columns="errorID",
                    values="value",
                    fill_value=0,
                )

                error_24h = error_pivot.rolling(window="24h").sum().reset_index()
                error_24h.columns = ["datetime"] + [f"{col}count" for col in error_pivot.columns]

                features_df = features_df.merge(error_24h, on="datetime", how="left")

            for i in range(1, 6):
                col = f"error{i}count"
                if col not in features_df.columns:
                    features_df[col] = 0
                else:
                    features_df[col] = features_df[col].fillna(0)

            maint_df = self.fetch_maintenance_data(device_id, start_date=cutoff_date)
            if not maint_df.empty:
                maint_df = maint_df.dropna(subset=["comp"]).assign(
                    datetime=pd.to_datetime(maint_df["datetime"]),
                )

            if not maint_df.empty:
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

            machines_df = self.fetch_machines_data(device_id)
            features_df["age"] = int(machines_df["age"].iloc[0]) if not machines_df.empty else 10

            labels = None
            if include_failures:
                failures_df = self.fetch_failure_data(device_id, start_date=cutoff_date)
                if not failures_df.empty:
                    failure_df = pd.DataFrame(
                        {
                            "datetime": pd.to_datetime(failures_df["datetime"]).dt.floor("3h"),
                            "failure_component": failures_df["failure"].fillna("none"),
                        }
                    )
                    features_with_labels = features_df.merge(failure_df, on="datetime", how="left")
                    labels = features_with_labels["failure_component"].fillna("none")

                    features_df = features_with_labels.drop("failure_component", axis=1)

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
        sensor_key: str | List[str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int | None = None,
        desc: bool = True,
        group_by: Optional[str] = None,
    ) -> pd.DataFrame:
        """Fetch time series data via ThingsBoard API, DB-fetch-compatible schema.

        sensor_key accepts one key or many (list, or comma-separated string) —
        multiple keys are still fetched in a single TB API call.
        """
        keys = sensor_key if isinstance(sensor_key, list) else (sensor_key or "").split(",")
        keys = [k.strip() for k in keys if k.strip()]
        if not keys:
            logger.error("Sensor key is required for fetching time series data")
            return pd.DataFrame(columns=["datetime"])

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
            keys=",".join(keys),
        )

        def _row(record):
            if isinstance(record, dict):
                return record.get("ts"), record.get("value")
            return record.ts, record.value

        dfs = []
        for key in keys:
            records = ts.get(key, [])
            logger.info(
                f"Fetched {len(records)} rows from ThingsBoard API for device {device_id}, sensor {key}"
            )
            if not records:
                continue
            tss, values = zip(*(_row(r) for r in records))
            dfs.append(
                pd.DataFrame(
                    {"datetime": pd.to_datetime(tss, unit="ms"), key: [float(v) for v in values]}
                )
            )

        if not dfs:
            return pd.DataFrame(columns=["datetime"] + keys)

        df = reduce(lambda left, right: left.merge(right, on="datetime", how="outer"), dfs)
        return (
            df.drop_duplicates(subset=["datetime"], keep="last")
            .sort_values("datetime")
            .reset_index(drop=True)
        )

    def fetch_device_sensors(self, device_id: str) -> List[str]:
        logger.info(f"Fetching available sensors for device {device_id}")

        try:
            sensors = get_client().get_timeseries_keys(entity_type="DEVICE", entity_id=device_id)
            logger.info(f"Found {len(sensors)} sensors for device {device_id}")
            return sensors

        except Exception as e:
            logger.error(f"Error fetching device sensors: {e}")
            raise

    def fetch_all_devices(self) -> List[Dict[str, str]]:
        logger.info("Fetching all devices")

        try:
            page = get_client().get_tenant_devices(page_size=1000, page=0)
            raw_devices = (
                page.get("data", [])
                if isinstance(page, dict)
                else getattr(page, "data", page or [])
            )
            devices = [
                {
                    "id": self._model_id(
                        device.get("id")
                        if isinstance(device, dict)
                        else getattr(device, "id", None)
                    ),
                    "name": (
                        device.get("name")
                        if isinstance(device, dict)
                        else getattr(device, "name", None)
                    ),
                    "type": (
                        device.get("type")
                        if isinstance(device, dict)
                        else getattr(device, "type", None)
                    ),
                }
                for device in raw_devices
            ]

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

        # ponytail: original SQL never filtered by device_id (likely a pre-existing bug);
        # the TB API is entity-scoped, so device_id is now required to fetch anything.
        if not device_id:
            logger.error(f"device_id is required to fetch sensor '{sensor_key}' via the TB API")
            return pd.DataFrame(columns=["datetime", sensor_key])

        try:
            return self.api_fetch_time_series_data(
                device_id=device_id,
                sensor_key=sensor_key,
                start_date=start_date,
                limit=limit,
                desc=True,
            )

        except Exception as e:
            logger.error(f"Error fetching sensor data: {e}")
            return pd.DataFrame(columns=["datetime", "value"])

    def _fetch_failure_labels(
        self, device_id: str, start_ts: int, end_ts: int, index: pd.Index
    ) -> pd.Series:
        key = "failure_within_24h"
        ts = get_client().get_timeseries_history(
            entity_type="DEVICE",
            entity_id=device_id,
            start_ts=start_ts,
            end_ts=end_ts,
            order_by="ASC",
            limit=str(1_000_000),
            keys=key,
        )
        records = ts.get(key, [])

        def _row(record):
            return (
                (record.get("ts"), record.get("value"))
                if isinstance(record, dict)
                else (record.ts, record.value)
            )

        # ponytail: replicates the old bool_v/str_v/long_v CASE — any of true/"true"/1 counts as a failure
        def _is_failure(value) -> int:
            return int(str(value).strip().lower() in ("true", "1", "1.0"))

        failures = [
            {"timestamp": pd.to_datetime(ts_ms, unit="ms"), "failure": _is_failure(value)}
            for ts_ms, value in (_row(r) for r in records)
        ]

        if not failures:
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
            get_client().get_tenant_devices(page_size=1, page=0)
            get_quarkus_client().get_available_models()
            return True
        except Exception as e:
            logger.error(f"API connection test failed: {e}")
            return False

    def close(self) -> None:
        logger.info("DataRegistry uses API clients; no database connection to close")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return "DataRegistry(source='api')"
