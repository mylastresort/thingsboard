from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from library.core.data_registry import DataRegistry


class TestDataRegistryInit:
    def test_defaults(self):
        dr = DataRegistry()
        assert dr.telemetry_keys == ["volt", "rotate", "pressure", "vibration"]
        assert dr.error_keys == [f"error{i}" for i in range(1, 6)]
        assert dr.component_keys == ["comp1", "comp2", "comp3", "comp4"]

    def test_custom_keys(self):
        dr = DataRegistry(
            telemetry_keys=["t1", "t2"],
            error_keys=["e1"],
            component_keys=["c1", "c2", "c3"],
        )
        assert dr.telemetry_keys == ["t1", "t2"]
        assert dr.error_keys == ["e1"]
        assert dr.component_keys == ["c1", "c2", "c3"]


class TestDataRegistryHelpers:
    def test_get_key_ids(self):
        dr = DataRegistry(telemetry_keys=["a", "b", "c"])
        ids = dr._get_key_ids(["a", "b", "c"])
        assert ids == [0, 1, 2]

    def test_start_ts(self):
        dr = DataRegistry()
        dt = datetime(2024, 1, 1, 0, 0, 0)
        assert dr._start_ts(dt) == int(dt.timestamp() * 1000)
        assert dr._start_ts(None) is None

    def test_end_ts(self):
        dr = DataRegistry()
        dt = datetime(2024, 6, 15, 12, 0, 0)
        assert dr._end_ts(dt) == int(dt.timestamp() * 1000)
        assert dr._end_ts(None) is None

    def test_model_id_none(self):
        dr = DataRegistry()
        assert dr._model_id(None) is None

    def test_model_id_dict(self):
        dr = DataRegistry()
        assert dr._model_id({"id": "abc"}) == "abc"
        assert dr._model_id({"entityId": "xyz"}) == "xyz"
        assert dr._model_id({"value": "val"}) == "val"

    def test_model_id_string(self):
        dr = DataRegistry()
        assert dr._model_id("hello") == "hello"

    def test_model_id_object(self):
        dr = DataRegistry()
        obj = MagicMock()
        obj.id = "obj_id"
        assert dr._model_id(obj) == "obj_id"

    def test_record_datetime(self):
        dr = DataRegistry()
        assert dr._record_datetime({"datetime": "2024-01-01"}) == "2024-01-01"
        assert dr._record_datetime({"dateTime": "2024-06-01"}) == "2024-06-01"
        assert dr._record_datetime({}) is None

    def test_naive_datetime(self):
        dr = DataRegistry()
        ts = dr._naive_datetime("2024-01-01")
        assert ts.tzinfo is None

    def test_repr(self):
        dr = DataRegistry()
        assert "api" in repr(dr)

    def test_context_manager(self):
        dr = DataRegistry()
        with dr as ctx:
            assert ctx is dr

    def test_close(self):
        dr = DataRegistry()
        dr.close()

    def test_get_key_id(self):
        dr = DataRegistry()
        assert dr._get_key_id("any_key") is None


class TestDataRegistryFetchMaintenanceData:
    @patch("library.core.data_registry.get_quarkus_client")
    def test_empty_history(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [], "errors": [], "failures": []
        }
        dr = DataRegistry()
        result = dr.fetch_maintenance_data(
            "dev1",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )
        assert isinstance(result, pd.DataFrame)
        assert result.empty or len(result) == 0

    @patch("library.core.data_registry.get_quarkus_client")
    def test_with_maintenance_records(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [
                {"dateTime": "2024-01-01T00:00:00", "parts_replaced": "comp1"},
                {"dateTime": "2024-01-02T00:00:00", "parts_replaced": "comp2"},
            ],
            "errors": [],
            "failures": [],
        }
        dr = DataRegistry()
        result = dr.fetch_maintenance_data(
            "dev1",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 1),
        )
        assert len(result) == 2
        assert "datetime" in result.columns
        assert "comp" in result.columns


class TestDataRegistryFetchErrorData:
    @patch("library.core.data_registry.get_quarkus_client")
    def test_empty_history(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [], "errors": [], "failures": []
        }
        dr = DataRegistry()
        result = dr.fetch_error_data(
            "dev1",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )
        assert isinstance(result, pd.DataFrame)

    @patch("library.core.data_registry.get_quarkus_client")
    def test_with_error_records(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [],
            "errors": [
                {"dateTime": "2024-01-01T00:00:00", "error_code": "error1"},
                {"dateTime": "2024-01-02T00:00:00", "error_code": "error3"},
            ],
            "failures": [],
        }
        dr = DataRegistry()
        result = dr.fetch_error_data(
            "dev1",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 1),
        )
        assert len(result) == 2
        assert "datetime" in result.columns
        assert "errorID" in result.columns


class TestDataRegistryFetchFailureData:
    @patch("library.core.data_registry.get_quarkus_client")
    def test_empty_history(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [], "errors": [], "failures": []
        }
        dr = DataRegistry()
        result = dr.fetch_failure_data(
            "dev1",
            start_date=datetime(2020, 1, 1),
            end_date=datetime(2024, 1, 1),
        )
        assert isinstance(result, pd.DataFrame)

    @patch("library.core.data_registry.get_quarkus_client")
    def test_with_failure_records(self, mock_qc):
        mock_qc.return_value.get_failure_mode_history.return_value = {
            "maintenance": [],
            "errors": [],
            "failures": [
                {"dateTime": "2024-01-01T00:00:00", "root_cause": "comp1"},
                {"dateTime": "2024-01-05T00:00:00", "root_cause": "comp3"},
            ],
        }
        dr = DataRegistry()
        result = dr.fetch_failure_data(
            "dev1",
            start_date=datetime(2024, 1, 1),
            end_date=datetime(2024, 6, 1),
        )
        assert len(result) == 2
        assert "datetime" in result.columns
        assert "failure" in result.columns


class TestDataRegistryFetchMachinesData:
    @patch("library.core.data_registry.get_client")
    def test_default_values(self, mock_client):
        mock_client.return_value.get_attributes_by_scope.side_effect = AttributeError("no")
        mock_client.return_value.get_attributes.return_value = []
        dr = DataRegistry()
        result = dr.fetch_machines_data("dev1")
        assert len(result) == 1
        assert result["age"].iloc[0] == 10
        assert result["model"].iloc[0] == "model3"


class TestDataRegistryTestConnection:
    @patch("library.core.data_registry.get_client")
    @patch("library.core.data_registry.get_quarkus_client")
    def test_success(self, mock_qc, mock_client):
        dr = DataRegistry()
        assert dr.test_connection() is True

    @patch("library.core.data_registry.get_client")
    @patch("library.core.data_registry.get_quarkus_client")
    def test_failure(self, mock_qc, mock_client):
        mock_client.return_value.get_tenant_devices.side_effect = Exception("conn error")
        dr = DataRegistry()
        assert dr.test_connection() is False
