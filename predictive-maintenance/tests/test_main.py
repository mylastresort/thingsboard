import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import app
from src.db_connector import get_db_connection, setup_model_database

# Use a separate test database
DATABASE_URL = "postgresql://model_user:model_pass@localhost:5433/model_db_test"

engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Override the get_db_connection dependency to use the test database
def override_get_db_connection():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db_connection] = override_get_db_connection


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    # Create the test database tables
    setup_model_database()
    yield
    # You can add teardown logic here if needed, e.g., dropping tables


client = TestClient(app)


def test_create_forecast():
    response = client.post(
        "/api/v1/forecast",
        json={
            "name": "dsa",
            "deviceId": {"entityType": "DEVICE", "id": "9f45fd90-0b66-11f1-add6-958e4a75fa7a"},
            "additionalData": "{}",
            "anomalyAlgorithm": "random_forest",
            "anomalyEndDate": 1781909999999,
            "anomalyStartDate": 1776639600000,
            "attributes": [{"key": "vibration", "aggregation": "average", "groupByMs": 5000}],
            "forecastAlgorithm": "lstm",
            "forecastEndDate": 1781909999999,
            "forecastStartDate": 1779231600000,
            "viewPreferences": '{"hidden":false}',
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "dsa"
    assert data["deviceId"]["id"] == "9f45fd90-0b66-11f1-add6-958e4a75fa7a"
    assert "id" in data
