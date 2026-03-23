from fastapi.testclient import TestClient
from app.main import app  # adjust if different

client = TestClient(app)


def test_get_applicants():
    response = client.get("/api/health")

    assert response.status_code == 200
