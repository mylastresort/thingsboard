try:
    from ..algorithms.factory import AlgorithmRegistry
    from ..core.model_interface import BaseModel
    from ..core.types import AlgorithmType, SupervisedConfig, TaskType
except ImportError:
    import sys
    from pathlib import Path

    _file_path = Path(__file__).resolve()
    _predictive_maintenance_path = _file_path.parent.parent.parent
    if str(_predictive_maintenance_path) not in sys.path:
        sys.path.insert(0, str(_predictive_maintenance_path))

    from library.algorithms.factory import AlgorithmRegistry
    from library.core.model_interface import BaseModel
    from library.core.types import AlgorithmType, SupervisedConfig, TaskType

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

from src.logger import logger

pd.set_option("display.max_columns", None)


class AnomalyPredictor(BaseModel):
    def __init__(
        self,
        name: str = "anomaly_predictor",
        algorithm_name: str = "random_forest",
        algorithm_hyperparams: Optional[Dict[str, Any]] = None,
        data_registry=None,
        device_id: str | None = None,
        additional_info: Optional[Dict[str, Any]] = None,
        sensors: Optional[List[str]] = None,
        train_start_date=datetime.now() - pd.Timedelta(days=365 * 2),
        train_end_date=datetime.now(),
    ):
        super().__init__(name, data_registry=data_registry)
        self.algorithm_name = algorithm_name
        self.algorithm_hyperparams = algorithm_hyperparams or {}
        self.feature_columns = []
        self.device_id = device_id
        self.sensors = sensors or ["volt", "rotate", "pressure", "vibration"]
        self.additional_info = additional_info or {}
        self.train_start_date = train_start_date
        self.train_end_date = train_end_date

        self.algorithm = None

    def _build_feature_columns(
        self,
        telemetry_keys: List[str],
        error_keys: List[str],
        component_keys: List[str],
    ) -> List[str]:
        features = []

        for key in telemetry_keys:
            features.extend([f"{key}mean_3h", f"{key}sd_3h", f"{key}mean_24h", f"{key}sd_24h"])

        for i in range(1, len(error_keys) + 1):
            features.append(f"error{i}count")

        features.extend(component_keys)

        features.append("age")

        return features

    def fetch(self, device_id, **kwargs):
        if not self.data_registry:
            raise ValueError("No data registry available")

        start_date = kwargs.get("start_date", datetime(2015, 1, 1, 6, 0, 0))
        end_date = kwargs.get("end_date", None)

        telemetry_df = self.data_registry.fetch_telemetry_data(
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
            sensors=self.sensors,
        )
        telemetry_df["machineID"] = 1  # from dataset

        # fetch telemetry_df
        print("[PREDICITON JOB] telemetry_df DataFrame", flush=True)
        print(telemetry_df, flush=True)
        print("dataframe columns", flush=True)
        print(telemetry_df.columns, flush=True)

        failures_df = self.data_registry.fetch_failure_data(
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
        )
        failures_df["machineID"] = 1  # from dataset

        # fetch failures_df
        print("[PREDICITON JOB] failures_df DataFrame", flush=True)
        print(failures_df, flush=True)
        print("dataframe columns", flush=True)
        print(failures_df.columns, flush=True)

        maintenance_df = self.data_registry.fetch_maintenance_data(
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
        )

        maintenance_df["machineID"] = 1  # from dataset

        # fetch failures_df
        print("[PREDICITON JOB] maintenance_df DataFrame", flush=True)
        print(maintenance_df, flush=True)
        print("dataframe columns", flush=True)
        print(maintenance_df.columns, flush=True)

        machines_df = self.data_registry.fetch_machines_data(
            device_id=device_id,
        )

        machines_df["machineID"] = 1  # from dataset

        errors_df = self.data_registry.fetch_error_data(
            device_id=device_id,
            start_date=start_date,
            end_date=end_date,
        )

        errors_df["machineID"] = 1  # from dataset

        # fetch failures_df
        print("[PREDICITON JOB] errors_df DataFrame", flush=True)
        print(errors_df, flush=True)
        print("dataframe columns", flush=True)
        print(errors_df.columns, flush=True)

        return telemetry_df, failures_df, maintenance_df, machines_df, errors_df

    def fetch_latest(self, device_id, **kwargs):
        if not self.data_registry:
            raise ValueError("No data registry available")
        features_df, _ = self.data_registry.fetch_anomaly_training_data(
            device_id=device_id,
            days_back=550,
            include_failures=True,
            start_date=datetime(2015, 1, 5, 2, 0, 0),
        )
        if features_df.empty:
            raise ValueError(f"No data available for device {device_id}")
        latest_data = features_df.tail(1)
        latest_data = latest_data.fillna(0)
        if "failure_component" in latest_data.columns:
            latest_data = latest_data.drop("failure_component", axis=1)

        return latest_data

    def _generate_sample_data(self, n_samples=1000) -> pd.DataFrame:
        """
        FALLBACK: Generate synthetic sample data when real data is unavailable.
        """
        np.random.seed(42)
        data = {}

        for i in range(48):
            base_values = np.random.normal(75, 10, n_samples)
            failure_indices = np.random.choice(n_samples, size=int(n_samples * 0.1), replace=False)
            base_values[failure_indices] += np.random.normal(30, 10, len(failure_indices))
            data[f"sensor_{i:02d}"] = base_values

        sensor_avg = np.mean([data[f"sensor_{i:02d}"] for i in range(48)], axis=0)

        failure_component = np.full(n_samples, "none", dtype=object)
        failure_indices = sensor_avg > 90

        component_labels = ["comp1", "comp2", "comp3", "comp4"]
        failure_component[failure_indices] = np.random.choice(
            component_labels, size=np.sum(failure_indices)
        )

        data["failure_component"] = failure_component

        return pd.DataFrame(data)

    def train(self, data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        if "failure_component" not in data.columns:
            raise ValueError("Data must contain 'failure_component' target column")

        self.feature_columns = [col for col in data.columns if col != "failure_component"]

        logger.info(f"Training with {len(self.feature_columns)} features: {self.feature_columns}")

        if self.algorithm is None:
            hyperparams = self.algorithm_hyperparams.copy() if self.algorithm_hyperparams else {}
            hyperparams.pop("random_state", None)

            config = SupervisedConfig(
                name=self.algorithm_name,
                algorithm_type=AlgorithmType.SUPERVISED,
                task_type=TaskType.MULTICLASS_CLASSIFICATION,
                feature_columns=self.feature_columns,
                target_column="failure_component",
                hyperparameters=hyperparams,
            )

            self.algorithm = AlgorithmRegistry.create(config)
            self.add_algorithm("main", self.algorithm)

        results = {}
        training_start = datetime.now()

        X = data[self.feature_columns]
        y_raw = data["failure_component"]

        self.label_encoder = LabelEncoder()
        y = self.label_encoder.fit_transform(y_raw)

        self.class_labels = self.label_encoder.classes_
        logger.info(f"Class mapping: {dict(enumerate(self.class_labels))}")

        metrics = self.algorithm.train(X, y)

        results["main"] = {
            "accuracy": metrics.accuracy,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "f1_score": metrics.f1_score,
            "roc_auc": metrics.roc_auc,
            "training_time": metrics.training_time,
        }

        self.is_trained = True
        self.last_updated = datetime.now()

        results["overall"] = {
            "total_features": len(self.feature_columns),
            "feature_names": self.feature_columns,
            "average_accuracy": metrics.accuracy,
            "average_f1_score": metrics.f1_score,
            "total_training_time": (datetime.now() - training_start).total_seconds(),
        }

        return results

    def predict(self, data: pd.DataFrame, threshold: float = 0.5, **kwargs) -> Dict[str, Any]:
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")

        if not self.algorithm:
            raise ValueError("Algorithm not initialized. Train the model first.")

        missing_features = set(self.feature_columns) - set(data.columns)
        if missing_features:
            raise ValueError(f"Data missing feature columns: {missing_features}")

        X = data[self.feature_columns]
        output = self.algorithm.predict(X)

        predictions_encoded = output.predictions
        probabilities = output.probabilities

        if hasattr(self, "label_encoder") and hasattr(self, "class_labels"):
            predictions = self.label_encoder.inverse_transform(predictions_encoded)
            classes = self.class_labels
        else:
            predictions = predictions_encoded
            classes = ["none", "comp1", "comp2", "comp3", "comp4"]

        component_probs_list = []
        for i in range(len(predictions)):
            sample_probs = {}
            for j, cls in enumerate(classes):
                sample_probs[str(cls)] = float(probabilities[i, j])
            component_probs_list.append(sample_probs)

        failure_probs = []
        for probs in component_probs_list:
            failure_prob = 1.0 - probs.get("none", 0.0)
            failure_probs.append(failure_prob)

        filtered_predictions = [str(p) for p in predictions if str(p) != "none"]

        return {
            "predicted_components": filtered_predictions,
            "component_probabilities": component_probs_list,
            "failure_probabilities": failure_probs,
            "n_samples": len(data),
            "features_used": self.feature_columns,
            "prediction_time": datetime.now().isoformat(),
            "classes": [str(c) for c in classes],
        }

    def predict_single_machine(
        self, feature_dict: Dict[str, float], threshold: float = 0.5
    ) -> Dict[str, Any]:
        data = pd.DataFrame([feature_dict])

        result = self.predict(data, threshold)

        if result["predicted_components"]:
            predicted_component = result["predicted_components"][0]
            will_fail = True
        else:
            predicted_component = None
            will_fail = False

        return {
            "predicted_component": predicted_component,
            "component_probabilities": result["component_probabilities"][0],
            "failure_probability": result["failure_probabilities"][0],
            "will_fail": will_fail,
            "features_used": result["features_used"],
            "prediction_time": result["prediction_time"],
            "classes": result["classes"],
        }

    def save(self, path):
        super().save(path)

        path = Path(path)
        if hasattr(self, "label_encoder") and hasattr(self, "class_labels"):
            joblib.dump(
                {
                    "label_encoder": self.label_encoder,
                    "class_labels": self.class_labels,
                },
                path / "label_encoder.pkl",
            )

    def load(self, path):
        path = Path(path)

        metadata = joblib.load(path / "metadata.pkl")
        self.name = metadata["name"]
        self.is_trained = metadata["is_trained"]
        self.created_at = metadata["created_at"]
        self.last_updated = metadata.get("last_updated")

        if "main" in metadata["algorithm_keys"]:
            algorithm_path = path / "algorithm_main.pkl"

            algorithm_data = joblib.load(algorithm_path)
            loaded_config = algorithm_data["config"]

            self.algorithm = AlgorithmRegistry.create(loaded_config)

            self.algorithm.load(algorithm_path)

            self.add_algorithm("main", self.algorithm)

            self.feature_columns = loaded_config.feature_columns
        else:
            raise ValueError("Algorithm 'main' not found in loaded model")

        label_encoder_path = path / "label_encoder.pkl"
        if label_encoder_path.exists():
            encoder_data = joblib.load(label_encoder_path)
            self.label_encoder = encoder_data["label_encoder"]
            self.class_labels = encoder_data["class_labels"]
        else:
            pass


def create_3h_mean_features(telemetry, fields=["volt", "rotate", "pressure", "vibration"]):
    temp = []
    for col in fields:
        temp.append(
            pd.pivot_table(telemetry, index="datetime", columns="machineID", values=col)
            .resample("3h", closed="left", label="right")
            .mean()
            .unstack()
        )
    telemetry_mean_3h = pd.concat(temp, axis=1)
    telemetry_mean_3h.columns = [i + "mean_3h" for i in fields]
    telemetry_mean_3h.reset_index(inplace=True)

    temp = []
    for col in fields:
        temp.append(
            pd.pivot_table(telemetry, index="datetime", columns="machineID", values=col)
            .resample("3h", closed="left", label="right")
            .std()
            .unstack()
        )
    telemetry_sd_3h = pd.concat(temp, axis=1)
    telemetry_sd_3h.columns = [i + "sd_3h" for i in fields]
    telemetry_sd_3h.reset_index(inplace=True)
    return telemetry_mean_3h, telemetry_sd_3h


def create_24h_mean_features(telemetry, fields=["volt", "rotate", "pressure", "vibration"]):
    temp = []
    for col in fields:
        temp.append(
            pd.pivot_table(telemetry, index="datetime", columns="machineID", values=col)
            .resample("3h", closed="left", label="right")
            .first()
            .unstack()
            .rolling(window=24, center=False)
            .mean()
        )
    telemetry_mean_24h = pd.concat(temp, axis=1)
    telemetry_mean_24h.columns = [i + "mean_24h" for i in fields]
    telemetry_mean_24h.reset_index(inplace=True)
    telemetry_mean_24h = telemetry_mean_24h.loc[-telemetry_mean_24h["voltmean_24h"].isnull()]

    temp = []
    for col in fields:
        temp.append(
            pd.pivot_table(telemetry, index="datetime", columns="machineID", values=col)
            .resample("3h", closed="left", label="right")
            .first()
            .unstack()
            .rolling(window=24, center=False)
            .std()
        )
    telemetry_sd_24h = pd.concat(temp, axis=1)
    telemetry_sd_24h.columns = [i + "sd_24h" for i in fields]
    telemetry_sd_24h.reset_index(inplace=True)
    telemetry_sd_24h = telemetry_sd_24h.loc[-telemetry_sd_24h["voltsd_24h"].isnull()]
    return telemetry_mean_24h, telemetry_sd_24h


def create_telemetry_features(telemetry, fields=["volt", "rotate", "pressure", "vibration"]):
    print("[TRAIN_ANOMALY_MODEL] create_telemetry_features", flush=True)
    telemetry_mean_3h, telemetry_sd_3h = create_3h_mean_features(telemetry, fields)
    telemetry_mean_24h, telemetry_sd_24h = create_24h_mean_features(telemetry, fields)
    telemetry_feat = pd.concat(
        [
            telemetry_mean_3h,
            telemetry_sd_3h.iloc[:, 2:6],
            telemetry_mean_24h.iloc[:, 2:6],
            telemetry_sd_24h.iloc[:, 2:6],
        ],
        axis=1,
    ).dropna()
    print("[TRAIN_ANOMALY_MODEL] create_telemetry_features", flush=True)
    print(telemetry_feat.head(), flush=True)
    return telemetry_feat


def create_error_count_features(telemetry, errors, error_classes):
    if errors is None or errors.empty:
        error_count = telemetry[["datetime", "machineID"]].copy()
        for ec in error_classes:
            error_count[ec] = 0
        error_count["datetime"] = pd.to_datetime(error_count["datetime"])
    else:
        error_count = pd.get_dummies(
            errors.set_index("datetime"), columns=["errorID"]
        ).reset_index()
        error_count = error_count.astype(int, errors="ignore")

        cols = list(error_count.columns)
        new_cols = []
        for c in cols:
            if c == "datetime" or c == "machineID":
                new_cols.append(c)
            else:
                if c.startswith("errorID_"):
                    new_cols.append(c.split("errorID_", 1)[1])
                elif c.startswith("errorID"):
                    new_cols.append(c.replace("errorID", ""))
                else:
                    new_cols.append(c)

        error_count.columns = new_cols

        for ec in error_classes:
            if ec not in error_count.columns:
                error_count[ec] = 0

        error_count["datetime"] = pd.to_datetime(error_count["datetime"])

        error_count = (
            telemetry[["datetime", "machineID"]]
            .merge(error_count, on=["machineID", "datetime"], how="left")
            .fillna(0.0)
        )

    temp = []
    fields = error_classes if error_classes else ["error%d" % i for i in range(1, 6)]
    for col in fields:
        temp.append(
            pd.pivot_table(error_count, index="datetime", columns="machineID", values=col)
            .resample("3h", closed="left", label="right")
            .first()
            .unstack()
            .rolling(window=24, center=False)
            .sum()
        )
    error_count = pd.concat(temp, axis=1)
    error_count.columns = [i + "count" for i in fields]
    error_count.reset_index(inplace=True)
    error_count = error_count.dropna()
    return error_count


def create_comp_replacement_features(telemetry, maint, components):
    telemetry["datetime"] = pd.to_datetime(telemetry["datetime"])
    maint["datetime"] = pd.to_datetime(maint["datetime"])

    comp_rep = pd.get_dummies(maint.set_index("datetime")).reset_index()
    comp_rep.columns = ["datetime", "machineID"] + components

    comp_rep = (
        telemetry[["datetime", "machineID"]]
        .merge(comp_rep, on=["datetime", "machineID"], how="outer")
        .fillna(0)
        .sort_values(by=["machineID", "datetime"])
    )

    for comp in components:
        comp_rep.loc[comp_rep[comp] < 1, comp] = 0
        comp_rep.loc[-comp_rep[comp].isnull(), comp] = comp_rep.loc[
            -comp_rep[comp].isnull(), "datetime"
        ]
        comp_rep[comp] = comp_rep[comp].fillna(method="ffill")

    comp_rep = comp_rep.loc[comp_rep["datetime"] > pd.to_datetime("2015-01-01")]

    for comp in components:
        comp_rep[comp] = (comp_rep["datetime"] - pd.to_datetime(comp_rep[comp])) / np.timedelta64(
            1, "D"
        )

    return comp_rep


def merge_features(telemetry_feat, error_count, comp_rep, machines, failures):
    final_feat = telemetry_feat.merge(error_count, on=["datetime", "machineID"], how="left")
    final_feat = final_feat.merge(comp_rep, on=["datetime", "machineID"], how="left")
    final_feat = final_feat.merge(machines, on=["machineID"], how="left")

    final_feat["datetime"] = pd.to_datetime(final_feat["datetime"])
    failures["datetime"] = pd.to_datetime(failures["datetime"])
    labeled_features = final_feat.merge(failures, on=["datetime", "machineID"], how="left")
    labeled_features = labeled_features.fillna(method="bfill", limit=7)
    labeled_features = labeled_features.fillna("none")
    return labeled_features


def create_targets(labeled_features, components=["comp1", "comp2", "comp3", "comp4"]):
    labeled_features = labeled_features.sort_values(["machineID", "datetime"]).reset_index(
        drop=True
    )

    target_columns = []
    for hour in range(1, 25):
        target_col = f"target_hour_{hour}_multiclass"
        labeled_features[target_col] = "none"
        target_columns.append(target_col)

        binary_target_col = f"target_hour_{hour}_binary"
        labeled_features[binary_target_col] = 0
        target_columns.append(binary_target_col)

        for machine_id in labeled_features["machineID"].unique():
            machine_data = labeled_features[labeled_features["machineID"] == machine_id].copy()
            machine_indices = machine_data.index

            for i, idx in enumerate(machine_indices):
                period_ahead = (hour - 1) // 3 + 1
                future_idx = i + period_ahead
                if future_idx < len(machine_indices):
                    future_failure = labeled_features.loc[machine_indices[future_idx], "failure"]

                    if future_failure != "none" and future_failure in components:
                        labeled_features.loc[idx, target_col] = future_failure
                        labeled_features.loc[idx, binary_target_col] = 1

    return labeled_features


feature_cols = [
    "voltmean_3h",
    "rotatemean_3h",
    "pressuremean_3h",
    "vibrationmean_3h",
    "voltsd_3h",
    "rotatesd_3h",
    "pressuresd_3h",
    "vibrationsd_3h",
    "voltmean_24h",
    "rotatemean_24h",
    "pressuremean_24h",
    "vibrationmean_24h",
    "voltsd_24h",
    "rotatesd_24h",
    "pressuresd_24h",
    "vibrationsd_24h",
    "error1count",
    "error2count",
    "error3count",
    "error4count",
    "error5count",
    "comp1",
    "comp2",
    "comp3",
    "comp4",
    "age",
]


def create_labeled_features_clean(labeled_features: pd.DataFrame):
    if "model" in labeled_features.columns:
        le_model = LabelEncoder()
        labeled_features["model_encoded"] = le_model.fit_transform(
            labeled_features["model"].astype(str)
        )
        if "model_encoded" not in feature_cols:
            feature_cols.append("model_encoded")

    labeled_features_clean = labeled_features.dropna(subset=feature_cols)
    return labeled_features_clean, feature_cols


def split_data(labeled_features_clean: pd.DataFrame, feature_cols: list):
    labeled_features_clean = labeled_features_clean.sort_values(
        by=["machineID", "datetime"]
    ).reset_index(drop=True)
    buffer = pd.Timedelta(hours=24)

    train_rows = int(0.7 * len(labeled_features_clean))
    train = labeled_features_clean.iloc[:train_rows]

    if train.empty:
        raise ValueError("Not enough data to split into train, val, test sets.")

    val_rows = int(0.5 * (len(labeled_features_clean) - train_rows))
    val = labeled_features_clean.iloc[train_rows : train_rows + val_rows]
    val = val[val["datetime"] > (train["datetime"].max() + buffer)]

    if val.empty:
        raise ValueError("Not enough data to split into train, val, test sets.")

    test = labeled_features_clean.iloc[train_rows + val_rows :]
    test = test[test["datetime"] > (val["datetime"].max() + buffer)]

    if test.empty:
        raise ValueError("Not enough data to split into train, val, test sets.")

    X_train = train[feature_cols]
    X_val = val[feature_cols]
    X_test = test[feature_cols]

    return train, val, test, X_train, X_val, X_test


key_hours = [1, 4, 8, 12, 16, 20, 24]


MAX_ANOMALY_TRAIN_WORKERS = int(os.getenv("PDM_ANOMALY_TRAIN_WORKERS", "4"))


def _train_hourly_pair(
    hour, train, X_train, algorithm
):
    models = {}

    multiclass_target = f"target_hour_{hour}_multiclass"
    binary_target = f"target_hour_{hour}_binary"

    y_train_mc = train[multiclass_target]
    y_train_bin = train[binary_target]

    if len(y_train_mc.value_counts()) > 1:
        if algorithm == "random_forest":
            rf_multiclass = RandomForestClassifier(
                n_estimators=100,
                max_depth=12,
                min_samples_split=8,
                min_samples_leaf=4,
                class_weight="balanced",
                random_state=42,
                n_jobs=2,
            )
        elif algorithm == "xgboost":
            le_mc = LabelEncoder()
            y_train_mc_enc = le_mc.fit_transform(y_train_mc.astype(str))

            rf_multiclass = XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                objective="multi:softprob",
                num_class=len(le_mc.classes_),
                use_label_encoder=False,
                eval_metric="mlogloss",
                random_state=42,
                n_jobs=2,
            )
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        if algorithm == "xgboost":
            rf_multiclass.fit(X_train, y_train_mc_enc)
            rf_multiclass._label_encoder = le_mc
        else:
            rf_multiclass.fit(X_train, y_train_mc)
        models[f"hour_{hour}_multiclass"] = rf_multiclass

    if len(y_train_bin.value_counts()) > 1:
        if algorithm == "random_forest":
            rf_binary = RandomForestClassifier(
                n_estimators=100,
                max_depth=12,
                min_samples_split=8,
                min_samples_leaf=4,
                class_weight="balanced",
                random_state=42,
                n_jobs=2,
            )
        elif algorithm == "xgboost":
            rf_binary = XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                objective="binary:logistic",
                use_label_encoder=False,
                eval_metric="logloss",
                random_state=42,
                n_jobs=2,
            )
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        rf_binary.fit(X_train, y_train_bin)
        models[f"hour_{hour}_binary"] = rf_binary

    return hour, models


def create_and_train_hourly_models(
    train,
    val,
    test,
    X_train,
    X_val,
    X_test,
    feature_cols,
    components,
    algorithm="random_forest",
):
    if algorithm not in ["random_forest", "xgboost"]:
        algorithm = "random_forest"

    total_hours = len(key_hours)
    max_workers = min(MAX_ANOMALY_TRAIN_WORKERS, total_hours)

    hourly_models = {}

    if max_workers <= 1:
        for hour in key_hours:
            _, pair = _train_hourly_pair(hour, train, X_train, algorithm)
            hourly_models.update(pair)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_train_hourly_pair, hour, train, X_train, algorithm): hour
                for hour in key_hours
            }
            for future in as_completed(futures):
                hour = futures[future]
                try:
                    _, pair = future.result()
                    hourly_models.update(pair)
                except Exception:
                    logger.exception(f"Failed to train hourly model for hour {hour}")

    return hourly_models


def predict_next_24h_hourly_failures(
    telemetry_data, labeled_features_clean, feature_cols_in, hourly_models
):
    if labeled_features_clean.empty:
        raise ValueError("labeled_features_clean is empty, cannot make predictions")

    labeled_features_clean = labeled_features_clean.sort_values(by="datetime").reset_index(
        drop=True
    )

    latest_row = labeled_features_clean.iloc[-1]
    start_dt = latest_row["datetime"]

    feature_vector = {}
    for col in feature_cols_in:
        if col in latest_row.index:
            val = latest_row[col]
            if isinstance(val, (np.integer, np.floating)):
                feature_vector[col] = float(val)
            else:
                feature_vector[col] = val
        else:
            feature_vector[col] = 0.0

    X_current = pd.DataFrame([feature_vector])[feature_cols_in]
    X_current = X_current.astype(float)

    predictions = {
        "prediction_start_datetime": str(start_dt),
        "current_telemetry": telemetry_data,
        "hourly_predictions": {},
    }

    for hour in range(1, 25):
        prediction_time = start_dt + pd.Timedelta(hours=hour)
        closest_key_hour = min(key_hours, key=lambda x: abs(x - hour))

        binary_model_key = f"hour_{closest_key_hour}_binary"
        multiclass_model_key = f"hour_{closest_key_hour}_multiclass"

        hour_prediction = {"datetime": str(prediction_time), "hour": hour}

        if binary_model_key in hourly_models:
            binary_model = hourly_models[binary_model_key]
            try:
                proba = binary_model.predict_proba(X_current)
                general_failure_prob = float(proba[0, 1])
                hour_prediction["general_failure_probability"] = round(general_failure_prob, 4)
                hour_prediction["failure_predicted"] = general_failure_prob > 0.5
            except Exception:
                hour_prediction["general_failure_probability"] = 0.0
                hour_prediction["failure_predicted"] = False
        else:
            hour_prediction["general_failure_probability"] = 0.0
            hour_prediction["failure_predicted"] = False

        if multiclass_model_key in hourly_models:
            multiclass_model = hourly_models[multiclass_model_key]
            try:
                component_probs = multiclass_model.predict_proba(X_current)[0]
                predicted_component = multiclass_model.predict(X_current)[0]
                class_names = list(getattr(multiclass_model, "classes_", []))

                component_prob_dict = {}
                for i, class_name in enumerate(class_names):
                    component_prob_dict[str(class_name)] = round(float(component_probs[i]), 4)

                hour_prediction["predicted_failing_component"] = str(predicted_component)
                hour_prediction["component_probabilities"] = component_prob_dict

                component_failures = {k: v for k, v in component_prob_dict.items() if k != "none"}
                hour_prediction["component_failure_probabilities"] = component_failures
            except Exception:
                hour_prediction["predicted_failing_component"] = "none"
                hour_prediction["component_probabilities"] = {"none": 1.0}
                hour_prediction["component_failure_probabilities"] = {}
        else:
            hour_prediction["predicted_failing_component"] = "none"
            hour_prediction["component_probabilities"] = {"none": 1.0}
            hour_prediction["component_failure_probabilities"] = {}

        predictions["hourly_predictions"][f"hour_{hour}"] = hour_prediction

    return predictions


def save_models(hourly_models: dict, model_path):
    path = Path(model_path)
    path.mkdir(parents=True, exist_ok=True)

    for model_key, model in hourly_models.items():
        joblib.dump(model, path / f"{model_key}.joblib")


def load_models(model_path):
    path = Path(model_path)
    hourly_models = {}

    for model_file in path.glob("hour_*.joblib"):
        model_key = model_file.stem
        model = joblib.load(model_file)
        hourly_models[model_key] = model

    return hourly_models


def preprocess_data(telemetry, errors, maint, failures, machines, components, error_classes):
    print(
        (
            f"[PREPROCESS_DATA] telemetry.shape={telemetry.shape} "
            f"errors.shape={errors.shape} maint.shape={maint.shape} "
            f"failures.shape={failures.shape}"
        ),
        flush=True,
    )
    telemetry["datetime"] = pd.to_datetime(telemetry["datetime"])
    telemetry_feat = create_telemetry_features(telemetry)
    error_count = create_error_count_features(telemetry, errors, error_classes)
    print("errors: \n", flush=True)
    print(error_count, flush=True)
    comp_rep = create_comp_replacement_features(telemetry, maint, components)
    labeled_features = merge_features(telemetry_feat, error_count, comp_rep, machines, failures)

    print("\n[DEBUG] After merge_features, failure column value_counts:", flush=True)
    print(labeled_features["failure"].value_counts(), flush=True)
    print("\n[DEBUG] Sample of labeled_features with failures:", flush=True)
    failure_rows = labeled_features[labeled_features["failure"] != "none"]
    print(f"  Found {len(failure_rows)} rows with failures", flush=True)

    labeled_features = create_targets(labeled_features)
    labeled_features_clean, feature_cols = create_labeled_features_clean(labeled_features)
    return labeled_features_clean, feature_cols


def train_model(
    telemetry,
    errors,
    maint,
    failures,
    machines,
    components,
    error_classes,
    algorithm="random_forest",
):
    print("\n[TRAIN_MODEL] Starting training process...", flush=True)
    labeled_features_clean, feature_cols = preprocess_data(
        telemetry, errors, maint, failures, machines, components, error_classes
    )
    print(f"Labeled features cleaned: {labeled_features_clean.shape}", flush=True)

    print("\n[DEBUG] Target distribution in FULL dataset (before split):", flush=True)
    for hour in [1, 4, 8, 12, 16, 20, 24]:
        target_col = f"target_hour_{hour}_multiclass"
        print(f"  {target_col}:", flush=True)
        print(f"    {labeled_features_clean[target_col].value_counts().to_dict()}", flush=True)

    train, val, test, X_train, X_val, X_test = split_data(labeled_features_clean, feature_cols)

    print(
        f"\n[DEBUG] Split sizes - train: {len(train)}, val: {len(val)}, test: {len(test)}",
        flush=True,
    )
    hourly_models = create_and_train_hourly_models(
        train, val, test, X_train, X_val, X_test, feature_cols, components, algorithm=algorithm
    )
    return hourly_models, feature_cols, labeled_features_clean


def predict_failure(
    sample_datetime,
    telemetry_data,
    telemetry,
    errors,
    maint,
    failures,
    machines,
    feature_cols,
    hourly_models,
    components,
    error_classes,
):
    labeled_features_clean, _ = preprocess_data(
        telemetry, errors, maint, failures, machines, components, error_classes
    )

    labeled_features_clean = labeled_features_clean[
        labeled_features_clean["datetime"] <= sample_datetime
    ]

    return predict_next_24h_hourly_failures(
        telemetry_data, labeled_features_clean, feature_cols, hourly_models
    )


if __name__ == "__main__":
    _current_file = Path(__file__).resolve()
    _base_path = None

    for _parent in [
        _current_file.parent.parent.parent.parent,
        _current_file.parent.parent.parent,
        _current_file.parent.parent,
    ]:
        _test_path = _parent / "application/src/main/resources/predictive-maintenance/data"
        if _test_path.exists():
            _base_path = _test_path
            break

    if _base_path is None:
        raise FileNotFoundError(
            f"Could not find data directory. Searched from {_current_file}\n"
            f"Please ensure you're running from within the thingsboard project."
        )

    base_path = _base_path

    telemetry = pd.read_csv(base_path / "PdM_telemetry.csv")
    errors = pd.read_csv(base_path / "PdM_errors.csv")
    maint = pd.read_csv(base_path / "PdM_maint.csv")
    failures = pd.read_csv(base_path / "PdM_failures.csv")
    machines = pd.read_csv(base_path / "PdM_machines.csv")

    cutoff = pd.to_datetime("2015-01-01 06:00:00")

    telemetry["datetime"] = pd.to_datetime(telemetry["datetime"], errors="coerce")
    telemetry = telemetry.loc[telemetry["datetime"] > cutoff].reset_index(drop=True)

    errors["datetime"] = pd.to_datetime(errors["datetime"], errors="coerce")
    errors = errors.loc[errors["datetime"] > cutoff].reset_index(drop=True)

    maint["datetime"] = pd.to_datetime(maint["datetime"], errors="coerce")
    maint = maint.loc[maint["datetime"] > cutoff].reset_index(drop=True)

    failures["datetime"] = pd.to_datetime(failures["datetime"], errors="coerce")
    failures = failures.loc[failures["datetime"] > cutoff].reset_index(drop=True)

    end_date = pd.to_datetime("2016-01-02 02:00:00")

    telemetry = telemetry[telemetry["machineID"] == 1]

    errors = errors[errors["machineID"] == 1]
    maint = maint[maint["machineID"] == 1]
    failures = failures[failures["machineID"] == 1]

    machines = machines[machines["machineID"] == 1]

    components = ["comp1", "comp2", "comp3", "comp4"]
    error_classes = ["error1", "error2", "error3", "error4", "error5"]
    hourly_models, feature_cols, labeled_features_clean = train_model(
        telemetry,
        errors,
        maint,
        failures,
        machines,
        components,
        error_classes,
        algorithm="random_forest",
    )

    sample_datetime = "2015-04-20 02:00:00"

    sample_telemetry = {"volt": 158, "rotate": 429, "pressure": 94, "vibration": 58}

    result1 = predict_failure(
        sample_datetime,
        sample_telemetry,
        telemetry,
        errors,
        maint,
        failures,
        machines,
        feature_cols,
        hourly_models,
        components,
        error_classes,
    )

    for hour in range(1, 25):
        hour_data = result1["hourly_predictions"][f"hour_{hour}"]
