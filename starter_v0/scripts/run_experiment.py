"""Run one real experiment at a time, preserving all measurements."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from env_loader import load_lab_env
from versioning import artifact_version_dict, build_artifact_version

SUITES = {"base": "eval_base.json", "group": "eval_group.json",
          "adversarial": "eval_adversarial.json", "extension": "eval_helpdesk_extension.json"}
KEYS = {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY"}


def record_run(payload: dict, run_path: Path) -> None:
    summary = payload["summary"]
    if summary["provider_error_cases"] or summary["measured_cases"] != summary["total_cases"]:
        raise ValueError("Incomplete provider run must not become a measured version row")
    path = ROOT / "artifacts" / "version_log.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    template = next(row for row in rows if row["version"] == payload["version"])
    row = dict(template)
    row.update({key: payload[key] for key in ("artifact_version", "prompt_hash", "tools_hash")})
    row.update(provider=payload["provider"], model=payload["model"], suite=payload["suite"],
               tool_choice=payload["tool_choice"], dataset_hash=payload["dataset_hash"],
               evaluator_hash=payload["evaluator_hash"], metric_before="",
               metric_after=summary["case_accuracy"], run_file=run_path.relative_to(ROOT).as_posix(),
               status="measured_requires_manual_review")
    # Never compare different models/suites/datasets/evaluator settings.
    previous_version = f"v{int(payload['version'][1:]) - 1}"
    previous = [old for old in rows if old["version"] == previous_version and old.get("run_file")
                and all(old.get(key) == str(row[key]) for key in
                        ("provider", "model", "suite", "tool_choice", "dataset_hash", "evaluator_hash"))]
    if previous:
        row["metric_before"] = previous[-1]["metric_after"]
    rows = [old for old in rows if not (old["version"] == row["version"] and not old.get("run_file"))]
    rows.append(row)
    fields = list(dict.fromkeys(key for old in rows for key in old))
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", choices=["v0", "v1", "v2", "v3"], required=True)
    parser.add_argument("--suite", choices=SUITES, default="base")
    parser.add_argument("--provider", choices=KEYS, default="openrouter")
    parser.add_argument("--model")
    parser.add_argument("--delay", type=float, default=0)
    parser.add_argument("--run", action="store_true", help="Call the real provider; omission only displays the plan")
    args = parser.parse_args()
    load_lab_env(ROOT)
    folder = ROOT / "artifacts" / "versions" / args.version
    prompt, tools = folder / "system_prompt.md", folder / "tools.yaml"
    artifact = build_artifact_version(args.version, prompt, tools)
    plan = json.loads((ROOT / "artifacts" / "experiment_plan.json").read_text(encoding="utf-8"))
    candidate = next(item for item in plan["versions"] if item["version"] == args.version)
    print(json.dumps({**artifact_version_dict(artifact), "suite": args.suite,
                      "hypothesis": candidate["hypothesis"], "mode": "live" if args.run else "plan",
                      "key_configured": bool(os.getenv(KEYS[args.provider]))}, indent=2))
    if not args.run:
        print("No API call made. Read the previous run before using --run for the next version.")
        return
    if not os.getenv(KEYS[args.provider]):
        raise SystemExit(f"Missing {KEYS[args.provider]}; no experiment ran and no metrics were written.")
    provider_args = ["--provider", args.provider] + (["--model", args.model] if args.model else [])
    subprocess.run([sys.executable, "scripts/preflight_provider.py", *provider_args, "--tools", str(tools)], cwd=ROOT, check=True)
    run_dir = ROOT / "runs"
    before = set(run_dir.glob("*.json"))
    completed = subprocess.run([sys.executable, "run_eval.py", *provider_args, "--version", args.version,
                    "--suite", args.suite, "--eval-cases", str(ROOT / "data" / SUITES[args.suite]),
                    "--system-prompt", str(prompt), "--tools", str(tools), "--delay", str(args.delay)], cwd=ROOT)
    if completed.returncode:
        raise SystemExit(completed.returncode)
    created = set(run_dir.glob("*.json")) - before
    if len(created) != 1:
        raise SystemExit("Expected one new run. Concurrent eval detected; review files manually.")
    run_path = created.pop()
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    record_run(payload, run_path)
    print(f"Recorded {run_path.name}. Inspect failures, tool errors, blocked writes and empty results before continuing.")


if __name__ == "__main__":
    main()
