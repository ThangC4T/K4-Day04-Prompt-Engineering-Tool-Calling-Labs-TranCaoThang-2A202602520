"""Validate local deliverables; live model evidence is a separate gate."""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jsonschema import Draft202012Validator
from run_eval import load_cases, validate_expected_tools
from tools import TOOL_FUNCTIONS, load_tool_declarations
from versioning import artifact_version_dict, build_artifact_version


def check_local() -> dict:
    declarations = load_tool_declarations(ROOT / "artifacts/tools.yaml")
    names = [tool["name"] for tool in declarations]
    assert len(names) >= 5 and len(names) == len(set(names)), "Missing or duplicate tool declarations"
    assert set(names) == set(TOOL_FUNCTIONS), "Registry/declarations differ"
    for tool in declarations:
        Draft202012Validator.check_schema(tool["parameters"])
        params = inspect.signature(TOOL_FUNCTIONS[tool["name"]]).parameters
        assert set(tool["parameters"]["properties"]) <= set(params), f"Invalid parameters: {tool['name']}"
    counts = {}
    for name, expected in [("base", 30), ("group", 10), ("helpdesk_extension", 10), ("adversarial", 12)]:
        path = ROOT / "data" / f"eval_{name}.json"
        cases = load_cases(path, "B")
        assert len(cases) == expected, f"Wrong case count: {name}"
        assert len({case["id"] for case in cases}) == len(cases), f"Duplicate IDs: {name}"
        validate_expected_tools(cases, declarations, path)
        if name == "group":
            assert sum("turns" in case for case in cases) == 5
            for case in cases:
                assert case.get("metadata", {}).get("what_it_tests"), "Missing rationale"
                if "turns" in case:
                    assert case["turns"][-1]["role"] == "user", "Last turn must be user"
                else:
                    assert case.get("query"), "Single-turn case needs query"
        counts[name] = len(cases)
    plan = json.loads((ROOT / "artifacts/experiment_plan.json").read_text(encoding="utf-8"))
    versions = {}
    for row in plan["versions"]:
        folder = ROOT / "artifacts/versions" / row["version"]
        value = artifact_version_dict(build_artifact_version(row["version"], folder / "system_prompt.md", folder / "tools.yaml"))
        for key in ("artifact_version", "prompt_hash", "tools_hash"):
            assert value[key] == row[key], f"Update experiment plan after editing {row['version']}"
        versions[row["version"]] = value["artifact_version"]
    assert len(set(versions.values())) == 4
    for name in ("system_prompt.md", "tools.yaml"):
        assert (ROOT / "artifacts" / name).read_bytes() == (ROOT / "artifacts/versions/v3" / name).read_bytes()
    manifest = json.loads((ROOT / "data/fixed_suite_hashes.json").read_text())
    for name, digest in manifest.items():
        assert hashlib.sha256((ROOT / "data" / name).read_bytes()).hexdigest() == digest, f"Fixed suite modified: {name}"
    return {"evidence_type": "local_static_validation", "tool_count": len(names),
            "case_counts": counts, "artifact_versions": versions,
            "live_provider_tested": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-live", action="store_true", help="Fail if complete provider evidence is absent")
    args = parser.parse_args()
    result = check_local()
    print(json.dumps(result, indent=2))
    if args.require_live:
        runs = [json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "runs").glob("*.json")]
        valid = [run for run in runs if run.get("evidence_type") == "live_provider_eval"
                 and run["summary"]["provider_error_cases"] == 0
                 and run["summary"]["measured_cases"] == run["summary"]["total_cases"]
                 and run.get("artifact_version") == result["artifact_versions"].get(run.get("version"))]
        needed = {(version, "base") for version in ("v0", "v1", "v2", "v3")} | {("v3", "group"), ("v3", "adversarial")}
        missing = needed - {(run["version"], run["suite"]) for run in valid}
        if missing:
            raise SystemExit(f"Live evidence missing: {sorted(missing)}")
        print("Provider run files exist. Manual report, transcript and team review still required.")


if __name__ == "__main__":
    main()
