import argparse
import json
import subprocess
import sys
from pathlib import Path

CASES = {
    "efim_ecommerce_60": {
        "algorithm": "efim",
        "algorithm_file": "/work/efim.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 8985,
    },

    "efim_ecommerce_80": {
        "algorithm": "efim",
        "algorithm_file": "/work/efim.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 11980,
    },

    "efim_ecommerce_100": {
        "algorithm": "efim",
        "algorithm_file": "/work/efim.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 14975,
    },

    "fhm_ecommerce_60": {
        "algorithm": "fhm",
        "algorithm_file": "/work/fhm.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 8985,
    },
}

parser = argparse.ArgumentParser()
parser.add_argument("--case", required=True, choices=CASES)
args = parser.parse_args()

case_id = args.case
c = CASES[case_id]

result_dir = Path("/work/next4_batch/results")
result_dir.mkdir(parents=True, exist_ok=True)
outfile = result_dir / f"{case_id}.json"

if outfile.exists():
    print(f"{case_id}: result already exists; skipping")
    sys.exit(0)

cmd = [
    sys.executable,
    "/work/run_baseline_huim.py",
    "--worker",
    "--algorithm", c["algorithm"],
    "--algorithm-file", c["algorithm_file"],
    "--dataset", c["dataset"],
    "--file", c["file"],
    "--min-utility", str(c["min_utility"]),
    "--sample-interval", "0.05",
    "--max-unique-items-unsafe", "22",
    "--max-transactions", str(c["max_transactions"]),
]

try:
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=129600,
    )

    stdout = p.stdout.strip()

    if p.returncode == 0 and stdout:
        try:
            result = json.loads(stdout)
        except Exception:
            result = {
                "status": "error",
                "returncode": p.returncode,
                "stdout": stdout,
                "stderr": p.stderr,
            }
    else:
        result = {
            "status": "error",
            "returncode": p.returncode,
            "stdout": stdout,
            "stderr": p.stderr,
        }

except subprocess.TimeoutExpired:
    result = {
        "status": "timeout",
        "timeout_seconds": 129600,
    }

record = {
    "case_id": case_id,
    "algorithm": c["algorithm"],
    "dataset": c["dataset"],
    "min_utility": c["min_utility"],
    "max_transactions": c["max_transactions"],
    "result": result,
}

outfile.write_text(
    json.dumps(record, indent=2),
    encoding="utf-8",
)

print(json.dumps(record, indent=2))
