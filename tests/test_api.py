import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app

CATALOG = """
<table><thead><tr><th>Course Code</th><th>Title</th><th>Credits</th>
<th>Prerequisites</th><th>Cross-listed</th></tr></thead><tbody>
<tr><td>TEST 1001</td><td>Intro</td><td>3</td><td>None</td><td></td></tr>
<tr><td>TEST 2001</td><td>Advanced</td><td>3</td><td>TEST-1001</td><td>ALTX-1001</td></tr>
<tr><td>ALTX 1001</td><td>Alternate</td><td>3</td><td></td><td></td></tr>
</tbody></table>
"""
TRANSCRIPT = """
<table><tr><th>Status</th><th>Course</th><th>Title</th><th>Grade</th>
<th>Term</th><th>Credits</th></tr>
<tr><td>Attempted</td><td>TEST-1001</td><td>Intro</td><td>F</td><td>25F</td><td>3</td></tr>
<tr><td>Completed</td><td>TEST-1001</td><td>Intro</td><td>P</td><td>26SP</td><td>0</td></tr>
<tr><td>Completed</td><td>TEST-1001</td><td>Intro</td><td>90</td><td>26SP</td><td>3</td></tr>
<tr><td>Completed</td><td>test 1001</td><td>Intro</td><td>A</td><td>26S</td><td>3</td></tr>
<tr><td>Completed</td><td>ALTX-1001</td><td>Alternate</td><td>A</td><td>26W</td><td>3</td></tr>
<tr><td>Planned</td><td>TEST-2001</td><td>Advanced</td><td></td><td></td><td></td></tr>
</table>
"""


@pytest.fixture
def client():
    base = os.getenv("API_URL")
    if base:
        with httpx.Client(base_url=base, timeout=10) as remote:
            yield remote
    else:
        with TestClient(app) as local:
            yield local


@pytest.fixture
def student(client):
    path = f"/api/v1/students/test-{uuid4().hex}"
    assert upload(client, path + "/history/import", TRANSCRIPT).json() == {
        "status": "success",
        "past_courses_imported": 4,
    }
    return path


def upload(client, path, html, content_type="text/html"):
    return client.post(path, files={"file": ("fixture.html", html, content_type)})


def set_plan(client, student, terms):
    courses = [{"course_code": "test-2001", "term": term} for term in terms]
    assert (
        client.put(student + "/plan", json={"planned_courses": courses}).status_code
        == 200
    )


def test_audit_rules(client, student):
    assert client.get("/").status_code == 200
    assert (
        upload(client, "/api/v1/admin/catalog/import", CATALOG).json()[
            "courses_imported"
        ]
        == 3
    )
    assert client.get("/api/v1/catalog/courses/test-2001").status_code == 200
    set_plan(client, student, ["26S", "26SP", "26W", "25F"])
    audit = student + "/audit-report"
    response = client.get(audit)
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "warning"
    assert [entry["term"] for entry in report["timeline_validation"]] == [
        "25F",
        "26W",
        "26SP",
    ]
    assert all(
        entry["errors"][0]["type"] == "MISSING_PREREQUISITE"
        for entry in report["timeline_validation"]
    )
    assert len(report["cross_list_violations"]) == 4
    assert all(
        issue["type"] == "CROSS_LIST_CONFLICT"
        for issue in report["cross_list_violations"]
    )
    assert report["credit_summary"] == {
        "total_earned": 6,
        "total_planned": 12,
        "total_remaining_for_graduation": 102,
    }
    assert client.get(audit, params={"strict": "true"}).json()["status"] == "failed"
    assert client.delete(student + "/plan").status_code == 204
    assert client.get(audit, params={"strict": "true"}).json()["status"] == "ok"


def test_student_lifecycle(client, student):
    record = {
        "course_code": "TEST-1001",
        "term": "26SP",
        "credits_earned": 3,
        "status": "Completed",
    }
    assert (
        client.put(student + "/history", json={"history": [record]}).status_code == 200
    )
    course = {"course_code": "TEST-2001", "term": "26F"}
    assert (
        client.post(student + "/plan", json={"planned_courses": [course]}).status_code
        == 200
    )
    profile = client.get(student + "/profile").json()
    assert profile["history"] == [record]
    assert profile["plan"] == [course]
    assert client.delete(student + "/history").status_code == 204
    assert client.get(student + "/profile").json()["history"] == []
    unknown = f"/api/v1/students/unknown-{uuid4().hex}"
    assert client.get(unknown + "/audit-report").status_code == 404
    assert client.delete(unknown + "/plan").status_code == 404


def test_invalid_uploads(client, student):
    catalog = "/api/v1/admin/catalog/import"
    assert upload(client, catalog, CATALOG, "text/plain").status_code == 400
    assert upload(client, catalog, "<html></html>").status_code == 400
    assert upload(client, catalog, b"\xff").status_code == 400
    assert (
        upload(client, student + "/history/import", "<html></html>").status_code == 400
    )
    assert upload(client, student + "/history/import", b"\xff").status_code == 400
    assert client.get("/api/v1/catalog/courses/NOPE9999").status_code == 404
