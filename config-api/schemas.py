from datetime import datetime
from typing import Any
from pydantic import BaseModel, field_validator
import json


class ConfigBase(BaseModel):
    name: str
    description: str | None = None
    data: dict[str, Any] = {}


class ConfigCreate(ConfigBase):
    pass


class ConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    data: dict[str, Any] | None = None


class ConfigResponse(ConfigBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConfigSerializedResponse(BaseModel):
    """Response with config data serialized as a JSON string (for export/import flows)."""

    id: str
    name: str
    description: str | None = None
    data_json: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_config(cls, config: "ConfigResponse") -> "ConfigSerializedResponse":
        return cls(
            id=config.id,
            name=config.name,
            description=config.description,
            data_json=json.dumps(config.data, default=str),
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


class ConfigImportRequest(BaseModel):
    """Import a config from a serialized JSON string."""

    name: str
    description: str | None = None
    data_json: str

    @field_validator("data_json")
    @classmethod
    def validate_data_json(cls, v: str) -> str:
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, dict):
                raise ValueError("data_json must serialize to a JSON object")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        return v

    def deserialize(self) -> dict[str, Any]:
        return json.loads(self.data_json)
