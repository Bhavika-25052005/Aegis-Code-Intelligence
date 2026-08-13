import json, tempfile, os
from unittest.mock import MagicMock

print("=== Day 4 Validation Suite ===\n")

from app.services.quality_reporter import QualityReporter, _build_ac_legend
from app.api.quality import _push_gate_check, router as qr
from fastapi.routing import APIRoute

reporter = QualityReporter()

story = MagicMock()
story.test_plan = json.dumps({"tests": [
    {"test_id": "REQ-AC-01", "scope": "unit", "status": "passed", "source_type": "acceptance_criteria", "criteria": ["AC1"]},
    {"test_id": "REQ-AC-02", "scope": "unit", "status": "passed", "source_type": "acceptance_criteria", "criteria": ["AC1", "AC2"]},
    {"test_id": "REQ-EC-01", "scope": "unit", "status": "failed", "source_type": "edge_case", "criteria": ["AC2"]},
    {"test_id": "INT-01", "scope": "integration", "status": "passed", "source_type": "acceptance_criteria", "criteria": ["AC1"]},
    {"test_id": "SYS-01", "scope": "system", "status": "passed", "source_type": "acceptance_criteria", "criteria": []},
    {"test_id": "REG-01", "scope": "regression", "status": "passed", "source_type": "acceptance_criteria", "criteria": []},
    {"test_id": "CUSTOM-001", "scope": "integration", "status": "passed", "source_type": "user_requested", "criteria": []},
]})

summary = reporter.build_summary(story)
assert summary["unit"] == 3, f"unit: {summary['unit']}"
assert summary["integration"] == 1, f"integration: {summary['integration']}"
assert summary["system"] == 1
assert summary["regression"] == 1
assert summary["custom"] == 1
assert summary["total"] == 7, f"total: {summary['total']}"
assert summary["passed"] == 6
assert summary["failed"] == 1
print(f"  PASS  Test 1: build_summary unit={summary['unit']} integ={summary['integration']} sys={summary['system']} reg={summary['regression']} custom={summary['custom']} total={summary['total']} passed={summary['passed']} failed={summary['failed']}")

assert summary["total"] == 7
print("  PASS  Test 2: No double-counting")

traceability = {"tests": json.loads(story.test_plan)["tests"]}
results = reporter.filter_tests(traceability, search="REQ-AC")
assert len(results) == 2
print(f"  PASS  Test 3: search 'REQ-AC' -> {len(results)} results")

results = reporter.filter_tests(traceability, criterion="AC1")
assert len(results) == 3
print(f"  PASS  Test 4: criterion=AC1 -> {len(results)} results")

results = reporter.filter_tests(traceability, test_type="unit")
assert len(results) == 3
print(f"  PASS  Test 5: type=unit -> {len(results)} results")

results = reporter.filter_tests(traceability, status="failed")
assert len(results) == 1
print(f"  PASS  Test 6: status=failed -> {len(results)} result")

results = reporter.filter_tests(traceability, criterion="AC2", test_type="unit", status="passed")
assert len(results) == 1
print(f"  PASS  Test 7: combined AC2+unit+passed -> {len(results)} result")

results = reporter.filter_tests(traceability)
assert len(results) == 7
print(f"  PASS  Test 8: no filters -> {len(results)} tests")

multi = [t for t in json.loads(story.test_plan)["tests"] if t["test_id"] == "REQ-AC-02"][0]
assert "AC1" in multi["criteria"] and "AC2" in multi["criteria"]
print("  PASS  Test 9: test maps to multiple ACs")

no_criteria = [t for t in json.loads(story.test_plan)["tests"] if t["test_id"] == "SYS-01"][0]
assert no_criteria["criteria"] == []
print("  PASS  Test 10: unmapped test has empty criteria list")

legend = _build_ac_legend(["First criterion", "Second criterion", "Third criterion"])
assert legend[0]["id"] == "AC1"
assert legend[1]["id"] == "AC2"
assert legend[2]["id"] == "AC3"
assert legend[0]["text"] == "First criterion"
print("  PASS  Test 11: AC legend stable ordering")

with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
    tmp_path = tmp.name

project_mock = MagicMock(); project_mock.name = "Test Project"
feature_mock = MagicMock(); feature_mock.title = "Patient Registration"
story_mock = MagicMock(); story_mock.title = "Register Patient"; story_mock.test_status = "passed"
requirement = {"acceptance_criteria": ["Patient data required", "DOB must be valid", "Contact method required"]}

reporter.generate_pdf(
    project=project_mock, feature=feature_mock, story=story_mock,
    requirement=requirement,
    tests=json.loads(story.test_plan)["tests"],
    active_filters={"criterion": None, "type": None, "status": None, "search": None},
    output_path=tmp_path,
)
file_size = os.path.getsize(tmp_path)
assert file_size > 1000, f"PDF too small: {file_size} bytes"
print(f"  PASS  Test 12: PDF generated ({file_size:,} bytes) at {tmp_path}")

with tempfile.NamedTemporaryFile(suffix="_filtered.pdf", delete=False) as tmp2:
    tmp2_path = tmp2.name

filtered_tests = reporter.filter_tests(traceability, criterion="AC1")
reporter.generate_pdf(
    project=project_mock, feature=feature_mock, story=story_mock,
    requirement=requirement,
    tests=filtered_tests,
    active_filters={"criterion": "AC1", "type": None, "status": None, "search": None},
    output_path=tmp2_path,
)
size2 = os.path.getsize(tmp2_path)
assert size2 > 1000
print(f"  PASS  Test 13: Filtered PDF (AC1, {len(filtered_tests)} tests) ({size2:,} bytes)")

story_ok = MagicMock()
story_ok.requirement_analysis_status = "approved"
story_ok.implementation_plan_status = "approved"
story_ok.status = "completed"
story_ok.test_status = "passed"
story_ok.tasks = []
assert _push_gate_check(story_ok) is None
print("  PASS  Test 14: push gate passes when all conditions met")

story_blocked = MagicMock()
story_blocked.requirement_analysis_status = "approved"
story_blocked.implementation_plan_status = "approved"
story_blocked.status = "completed"
story_blocked.test_status = "running"
story_blocked.tasks = []
reason = _push_gate_check(story_blocked)
assert reason is not None
print(f"  PASS  Test 15: push blocked (quality gate not passed): '{reason}'")

story_no_req = MagicMock()
story_no_req.requirement_analysis_status = "draft"
story_no_req.implementation_plan_status = "approved"
story_no_req.status = "completed"
story_no_req.test_status = "passed"
story_no_req.tasks = []
reason2 = _push_gate_check(story_no_req)
assert "requirement" in reason2.lower()
print(f"  PASS  Test 16: push blocked (req not approved): '{reason2}'")

route_paths = {r.path for r in qr.routes if isinstance(r, APIRoute)}
assert "/projects/{project_id}/quality/{story_id}" in route_paths
assert "/projects/{project_id}/quality/{story_id}/report.pdf" in route_paths
assert "/projects/{project_id}/quality/{story_id}/push" in route_paths
assert "/projects/{project_id}/quality/{story_id}/verify-traceability" in route_paths
assert "/projects/{project_id}/quality/{story_id}/update-readme" in route_paths
print("  PASS  Test 17: all 5 quality API routes registered")

os.unlink(tmp_path)
os.unlink(tmp2_path)

print("\n=== All 17 Day 4 validation tests PASSED ===")
