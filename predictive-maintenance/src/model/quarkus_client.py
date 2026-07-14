import os
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from quarkus_api_client.api.default_api import DefaultApi
from quarkus_api_client.api_client import ApiClient
from quarkus_api_client.configuration import Configuration
from quarkus_api_client.models.prediction_create_request import PredictionCreateRequest


class QuarkusApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        load_dotenv()
        self.base_url = (
            base_url or os.getenv("QUARKUS_API_URL", "http://tb-quarkus:8081/api/v1")
        ).rstrip("/")
        self.timeout = timeout

        configuration = Configuration(host=self.base_url)
        api_client = ApiClient(configuration)
        self.models = DefaultApi(api_client)

    def get_forecast(self, forecast_id: str) -> dict[str, Any]:
        return self.models.get_forecast(forecast_id, _request_timeout=self.timeout)

    def get_failure_mode_history(
        self,
        model_id: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> dict[str, Any]:
        history = self.models.get_failure_mode_history(
            model_id,
            start_ts=start_ts,
            end_ts=end_ts,
            _request_timeout=self.timeout,
        )
        return history.to_dict() if hasattr(history, "to_dict") else history

    def create_anomaly_history_prediction(
        self,
        model_id: str,
        prediction_type: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        request = PredictionCreateRequest(
            created_at=self._parse_datetime(body.get("createdAt")),
            created_time=body.get("createdTime"),
            prediction_time=self._parse_datetime(body.get("predictionTime")),
            prediction_value=body.get("predictionValue"),
        )
        return self.models.create_anomaly_history_prediction(
            model_id,
            prediction_type,
            request,
            _request_timeout=self.timeout,
        )

    def get_available_models(self) -> dict[str, Any]:
        return self.models.get_available_models(_request_timeout=self.timeout)

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None or isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


_client: QuarkusApiClient | None = None


def get_quarkus_client() -> QuarkusApiClient:
    global _client
    if _client is None:
        _client = QuarkusApiClient()
    return _client
