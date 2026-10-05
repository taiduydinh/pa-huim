import argparse
import json
import subprocess
import sys
from pathlib import Path

CASES = {
    "hui_chainstore_T3": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "chainstore",
        "file": "/work/datasets/chainstore.txt",
        "min_utility": 98000,
        "max_transactions": None,
    },
    "hui_chainstore_T2": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "chainstore",
        "file": "/work/datasets/chainstore.txt",
        "min_utility": 95000,
        "max_transactions": None,
    },
    "hui_chainstore_T1": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "chainstore",
        "file": "/work/datasets/chainstore.txt",
        "min_utility": 90000,
        "max_transactions": None,
    },
    "up_chainstore_T2": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "chainstore",
        "file": "/work/datasets/chainstore.txt",
        "min_utility": 95000,
        "max_transactions": None,
    },
    "up_chainstore_T1": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "chainstore",
        "file": "/work/datasets/chainstore.txt",
        "min_utility": 90000,
        "max_transactions": None,
    },
    "up_ecommerce_20": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 2995,
    },
    "up_accidents_T10": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "accidents",
        "file": "/work/datasets/accidents.txt",
        "min_utility": 30000000,
        "max_transactions": None,
    },
    "up_accidents_T9": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "accidents",
        "file": "/work/datasets/accidents.txt",
        "min_utility": 29000000,
        "max_transactions": None,
    },
    "hui_ecommerce_T3": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 175000,
        "max_transactions": None,
    },
    "up_ecommerce_40": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "ecommerce",
        "file": "/work/datasets/ecommerce.txt",
        "min_utility": 180000,
        "max_transactions": 5990,
    },
}

parser = argparse.ArgumentParser()
parser.add_argument("--case", required=True, choices=CASES)
args = parser.parse_args()

case_id = args.case
c = CASES[case_id]

outdir = Path("/work/next10_batch/results")
outdir.mkdir(parents=True, exist_ok=True)

outfile = outdir / f"{case_id}.json"

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
]

if c["max_transactions"] is not None:
    cmd += [
        "--max-transactions",
        str(c["max_transactions"])
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
