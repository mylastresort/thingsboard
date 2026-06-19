import pytest
from fastapi.testclient import TestClient
from main import app
from src.db_connector import setup_model_database

client = TestClient(app)

def test_get_forecasts_by_page():
    # Attempt to fetch page
    response = client.get("/forecast?pageSize=10&page=0")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "totalElements" in data
    assert "totalPages" in data
    assert "hasNext" in data
    print("GET /forecast works successfully!")
    print(data)

