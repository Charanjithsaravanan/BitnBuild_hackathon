import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DATABASE_URL"] = "sqlite:///./test_labforge.db"
os.environ["JWT_SECRET"] = "test-secret-change-me-123456789012345678901234"
os.environ["ENVIRONMENT"] = "development"
os.environ["TRUSTED_HOSTS"] = "localhost,127.0.0.1,testserver"

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


def fresh_client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def auth(c):
    r = c.post("/api/v1/auth/register", json={"email": "researcher@example.com", "password": "StrongPassword123!"})
    assert r.status_code == 201, r.text
    r = c.post("/api/v1/auth/login", data={"username": "researcher@example.com", "password": "StrongPassword123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def definition(require_consent=False):
    return {
        "settings": {
            "fullscreen": True,
            "randomize_trials": True,
            "collect_device_info": True,
            "prevent_back_navigation": True,
            "timing_diagnostics": True,
            "consent_required": require_consent,
            "consent_version": "v1",
            "consent_text": "I consent to participate in this research study.",
            "debrief_text": "Thank you for participating.",
            "counterbalance_groups": ["A", "B"],
        },
        "variables": {"score": 0},
        "blocks": [
            {"id": "intro", "type": "instruction", "text": "Press F or J", "duration_ms": None},
            {
                "id": "trials",
                "type": "trial_group",
                "data": {
                    "repetitions": 2,
                    "randomize": True,
                    "trials": [
                        {
                            "id": "t1",
                            "stimulus": {"kind": "text", "value": "BLUE"},
                            "duration_ms": None,
                            "expected_response": "f",
                        },
                        {
                            "id": "t2",
                            "stimulus": {"kind": "text", "value": "RED"},
                            "duration_ms": None,
                            "expected_response": "j",
                        },
                    ],
                },
            },
            {
                "id": "branch",
                "type": "branch",
                "data": {
                    "condition": "last_correct == true",
                    "true_target": "good",
                    "false_target": "bad",
                },
            },
            {"id": "good", "type": "instruction", "text": "Good", "duration_ms": None},
            {"id": "bad", "type": "instruction", "text": "Try again", "duration_ms": None},
            {"id": "done", "type": "instruction", "text": "Done", "duration_ms": None},
        ],
    }


def test_research_grade_flow():
    client = fresh_client()
    headers = auth(client)

    r = client.post("/api/v1/experiments", headers=headers, json={"name": "Research Demo", "definition": definition(True)})
    assert r.status_code == 201, r.text
    experiment = r.json()

    r = client.post(f"/api/v1/experiments/{experiment['id']}/publish", headers=headers)
    assert r.status_code == 200, r.text

    r = client.get(f"/api/v1/public/experiments/{experiment['slug']}")
    assert r.status_code == 200
    public = r.json()
    assert public["definition_hash"]

    # Consent is mandatory.
    r = client.post(f"/api/v1/public/experiments/{experiment['slug']}/sessions", json={"participant_code": "P001"})
    assert r.status_code == 403

    r = client.post(
        f"/api/v1/public/experiments/{experiment['slug']}/sessions",
        json={"participant_code": "P001", "consent_accepted": True, "consent_version": "v1"},
    )
    assert r.status_code == 201, r.text
    session = r.json()
    token = session["participant_token"]
    assert token
    assert len(session["execution_plan"]) == 9  # intro + 4 expanded trials + branch + three following blocks
    assert session["condition_group"] in {"A", "B"}
    participant_headers = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/public/sessions/me", headers=participant_headers)
    assert r.status_code == 200
    assert r.json()["id"] == session["id"]

    r = client.post(
        "/api/v1/public/sessions/me/timing-diagnostics",
        headers=participant_headers,
        json={
            "performance_now_resolution_ms": 0.001,
            "refresh_rate_hz": 60,
            "refresh_interval_ms": 16.667,
            "refresh_jitter_ms": 0.5,
            "calibration_samples": 120,
            "visibility_changes": 0,
            "timer_early_fire_ms": 0.0,
            "browser": "Chrome",
            "platform": "Windows",
            "diagnostics_version": "1.0",
        },
    )
    assert r.status_code == 200, r.text

    # Try a wrong block id: server must reject client tampering with the execution plan.
    r = client.post(
        "/api/v1/public/sessions/me/responses",
        headers=participant_headers,
        json={
            "trial_index": 0,
            "block_id": "not-a-real-step",
            "response_value": "f",
            "correct": True,
            "client_event_id": "bad-event-12345678",
        },
    )
    assert r.status_code == 400

    # Record a valid trial response.
    first = session["execution_plan"][1]
    r = client.post(
        "/api/v1/public/sessions/me/responses",
        headers=participant_headers,
        json={
            "trial_index": 1,
            "block_id": first["group_id"],
            "response_value": "f",
            "correct": True,
            "reaction_time_ms": 542.3,
            "client_event_id": "event-12345678",
            "stimulus_onset_perf_ms": 1000.5,
            "response_perf_ms": 1542.8,
            "client_duration_ms": 542.3,
            "metadata": {"key": "f"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["reaction_time_ms"] == 542.3

    # Duplicate client event is rejected.
    r = client.post(
        "/api/v1/public/sessions/me/responses",
        headers=participant_headers,
        json={
            "trial_index": 1,
            "block_id": first["group_id"],
            "response_value": "f",
            "correct": True,
            "client_event_id": "event-12345678",
        },
    )
    assert r.status_code == 409

    r = client.post("/api/v1/public/sessions/me/complete", headers=participant_headers)
    assert r.status_code == 200, r.text
    assert r.json()["response_count"] == 1
    assert r.json()["debrief_text"] == "Thank you for participating."

    r = client.get(f"/api/v1/experiments/{experiment['id']}/results.json", headers=headers)
    assert r.status_code == 200
    payload = r.json()
    assert payload["experiment"]["definition_hash"] == public["definition_hash"]
    assert payload["sessions"][0]["responses"][0]["reaction_time_ms"] == 542.3

    r = client.get(f"/api/v1/experiments/{experiment['id']}/audit", headers=headers)
    assert r.status_code == 200
    actions = {event["action"] for event in r.json()["events"]}
    assert {"experiment.create", "experiment.publish"}.issubset(actions)
