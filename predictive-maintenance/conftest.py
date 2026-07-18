import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.datasets import make_classification, make_regression

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


@pytest.fixture
def classification_data():
    X, y = make_classification(
        n_samples=200, n_features=10, n_informative=5, n_classes=2, random_state=42
    )
    return pd.DataFrame(X, columns=[f"feat_{i}" for i in range(10)]), pd.Series(y, name="target")


@pytest.fixture
def multiclass_data():
    X, y = make_classification(
        n_samples=300, n_features=10, n_informative=5, n_classes=4, n_clusters_per_class=1, random_state=42
    )
    return pd.DataFrame(X, columns=[f"feat_{i}" for i in range(10)]), pd.Series(y, name="target")


@pytest.fixture
def regression_data():
    X, y = make_regression(n_samples=200, n_features=10, n_informative=5, random_state=42)
    return pd.DataFrame(X, columns=[f"feat_{i}" for i in range(10)]), pd.Series(y, name="target")


@pytest.fixture
def time_series_data():
    n = 500
    timestamps = pd.date_range("2024-01-01", periods=n, freq="h")
    values = 50 + 10 * np.sin(2 * np.pi * np.arange(n) / 24) + np.random.normal(0, 2, n)
    return pd.DataFrame({"timestamp": timestamps, "value": values})


@pytest.fixture
def anomaly_training_df():
    np.random.seed(42)
    n = 500
    data = {}
    for key in ["volt", "rotate", "pressure", "vibration"]:
        data[f"{key}mean_3h"] = np.random.normal(75, 10, n)
        data[f"{key}sd_3h"] = np.random.normal(5, 2, n)
        data[f"{key}mean_24h"] = np.random.normal(75, 10, n)
        data[f"{key}sd_24h"] = np.random.normal(5, 2, n)
    for i in range(1, 6):
        data[f"error{i}count"] = np.random.poisson(0.5, n)
    for i in range(1, 5):
        data[f"comp{i}"] = np.random.uniform(0, 365, n)
    data["age"] = np.random.randint(1, 20, n)
    data["failure_component"] = np.random.choice(
        ["none", "comp1", "comp2", "comp3", "comp4"], n, p=[0.85, 0.04, 0.04, 0.04, 0.03]
    )
    return pd.DataFrame(data)


@pytest.fixture
def hourly_models_dict():
    from sklearn.ensemble import RandomForestClassifier

    models = {}
    classes = np.array(["none", "comp1", "comp2", "comp3", "comp4"])

    for hour in [1, 4, 8, 12, 16, 20, 24]:
        X_dummy = np.random.rand(100, 26)
        y_mc = np.random.choice(classes, 100)
        y_bin = np.random.choice([0, 1], 100, p=[0.9, 0.1])

        rf_mc = RandomForestClassifier(n_estimators=10, random_state=42, n_jobs=-1)
        rf_mc.fit(X_dummy, y_mc)
        models[f"hour_{hour}_multiclass"] = rf_mc

        rf_bin = RandomForestClassifier(n_estimators=10, random_state=42, n_jobs=-1)
        rf_bin.fit(X_dummy, y_bin)
        models[f"hour_{hour}_binary"] = rf_bin

    return models
