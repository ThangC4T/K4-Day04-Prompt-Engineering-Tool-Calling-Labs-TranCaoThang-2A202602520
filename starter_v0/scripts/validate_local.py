"""Write actual deterministic check results, separate from live LLM evidence."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.check_submission import check_local


def main() -> None:
    static = check_local()
    compile_run = subprocess.run([sys.executable, "-m", "compileall", "-q", "-x", r"(/|\\)(\.venv|__pycache__)(/|\\)", "."], cwd=ROOT)
    if compile_run.returncode:
        raise SystemExit(compile_run.returncode)
    run = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "checks", "-v"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = run.stdout + run.stderr
    count = re.search(r"Ran (\d+) tests?", output)
    payload = {
        "evidence_type": "deterministic_local_checks", "live_provider_tested": False,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0], "tests_run": int(count.group(1)) if count else None,
        "tests_passed": run.returncode == 0, "compile_passed": compile_run.returncode == 0,
        "command": "python -m unittest discover -s checks -v", "static_validation": static,
        "notice": "Provider and HTTP responses in tests are scripted doubles; this is not LLM evaluation evidence.",
        "source_hashes": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for folder in (ROOT, ROOT / "checks", ROOT / "providers", ROOT / "scripts")
                          for path in sorted(folder.glob("*.py"))},
        "test_output": output,
    }
    destination = ROOT / "validation" / "local_checks.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Local tests: {payload['tests_run']}; passed={payload['tests_passed']}; live_provider_tested=False")
    print("Saved validation/local_checks.json")
    if run.returncode:
        print(output)
        raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
