"""Tests for the Flask web application."""

import json

import pytest

from kitt.web.app import FLASK_AVAILABLE, _scan_results, create_app

pytestmark = pytest.mark.skipif(not FLASK_AVAILABLE, reason="flask not installed")


@pytest.fixture
def app(tmp_path):
    """Create a test Flask app with sample results."""
    # Create sample results
    results_dir = (
        tmp_path / "kitt-results" / "test-model" / "ollama" / "2025-01-01_120000"
    )
    results_dir.mkdir(parents=True)

    metrics = {
        "kitt_version": "1.2.1",
        "suite_name": "quick",
        "timestamp": "2025-01-01T12:00:00",
        "engine": "ollama",
        "model": "test-model",
        "passed": True,
        "total_benchmarks": 1,
        "passed_count": 1,
        "failed_count": 0,
        "total_time_seconds": 5.0,
        "results": [
            {
                "test_name": "throughput",
                "test_version": "1.0.0",
                "run_number": 1,
                "passed": True,
                "metrics": {"avg_tps": 50.0, "total_iterations": 5},
                "errors": [],
                "warmup_times": [],
            }
        ],
    }

    with open(results_dir / "metrics.json", "w") as f:
        json.dump(metrics, f)

    flask_app = create_app(str(tmp_path), legacy=True)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"KITT" in response.data
    assert b"test-model" in response.data


def test_api_results(client):
    response = client.get("/api/results")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["model"] == "test-model"


def test_api_result_detail(client):
    response = client.get("/api/results/0")
    assert response.status_code == 200
    data = response.get_json()
    assert data["engine"] == "ollama"


def test_api_result_not_found(client):
    response = client.get("/api/results/99")
    assert response.status_code == 404


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_empty_results(tmp_path):
    app = create_app(str(tmp_path), legacy=True)
    app.config["TESTING"] = True
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    assert b"No Results Found" in response.data


def test_scan_results(tmp_path):
    results = _scan_results(tmp_path)
    assert results == []


@pytest.fixture
def multi_app(tmp_path):
    """Create a test Flask app with multiple results for filtering tests."""
    for model, engine in [
        ("Qwen-7B", "vllm"),
        ("Qwen-7B", "ollama"),
        ("Llama-8B", "vllm"),
    ]:
        results_dir = tmp_path / "kitt-results" / model / engine / "2025-01-01_120000"
        results_dir.mkdir(parents=True)

        metrics = {
            "kitt_version": "1.2.1",
            "suite_name": "quick",
            "timestamp": "2025-01-01T12:00:00",
            "engine": engine,
            "model": model,
            "passed": True,
            "total_benchmarks": 1,
            "passed_count": 1,
            "failed_count": 0,
            "total_time_seconds": 5.0,
            "results": [
                {
                    "test_name": "throughput",
                    "test_version": "1.0.0",
                    "run_number": 1,
                    "passed": True,
                    "metrics": {"avg_tps": 50.0},
                    "errors": [],
                    "warmup_times": [],
                }
            ],
        }

        with open(results_dir / "metrics.json", "w") as f:
            json.dump(metrics, f)

    flask_app = create_app(str(tmp_path), legacy=True)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def multi_client(multi_app):
    return multi_app.test_client()


def test_filter_by_model(multi_client):
    response = multi_client.get("/?model=Qwen-7B")
    assert response.status_code == 200
    assert b"Qwen-7B" in response.data
    # Filtered results table should show 2 results (Qwen-7B with vllm + ollama)
    data = multi_client.get("/api/campaigns?model=Qwen-7B").get_json()
    assert len(data) == 2
    assert all(d["model"] == "Qwen-7B" for d in data)


def test_filter_by_engine(multi_client):
    response = multi_client.get("/?engine=vllm")
    assert response.status_code == 200
    assert b"vllm" in response.data
    # Both models use vllm
    assert b"Qwen-7B" in response.data
    assert b"Llama-8B" in response.data


def test_filter_by_model_and_engine(multi_client):
    response = multi_client.get("/?model=Qwen-7B&engine=vllm")
    assert response.status_code == 200
    assert b"Qwen-7B" in response.data


def test_filter_dropdowns_present(multi_client):
    response = multi_client.get("/")
    assert response.status_code == 200
    assert b"All Models" in response.data
    assert b"All Engines" in response.data


def test_api_campaigns(multi_client):
    response = multi_client.get("/api/campaigns")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 3
    models = {d["model"] for d in data}
    assert "Qwen-7B" in models
    assert "Llama-8B" in models


def test_api_campaigns_filtered(multi_client):
    response = multi_client.get("/api/campaigns?model=Qwen-7B")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert all(d["model"] == "Qwen-7B" for d in data)


def test_api_campaigns_filtered_by_engine(multi_client):
    response = multi_client.get("/api/campaigns?engine=vllm")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 2
    assert all(d["engine"] == "vllm" for d in data)
