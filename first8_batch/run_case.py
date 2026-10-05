import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/work")
OUT = ROOT / "first8_batch" / "results"

OUT.mkdir(parents=True, exist_ok=True)

CASES = {
    # 1
    "hui_chainstore_T7": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "chainstore",
        "min_utility": 261000,
        "max_transactions": None,
    },

    # 2
    "up_chainstore_T4": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "chainstore",
        "min_utility": 130000,
        "max_transactions": None,
    },

    # 3
    "fhm_accidents_80": {
        "algorithm": "fhm",
        "algorithm_file": "/work/fhm.py",
        "dataset": "accidents",
        "min_utility": 24000000,
        "max_transactions": 272146,
    },

    # 4
    "hui_chainstore_80": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "chainstore",
        "min_utility": 130000,
        "max_transactions": 890359,
    },

    # 5
    "up_chainstore_100": {
        "algorithm": "upgrowthplus",
        "algorithm_file": "/work/up_growthplus.py",
        "dataset": "chainstore",
        "min_utility": 130000,
        "max_transactions": 1112949,
    },

    # 6
    "hui_accidents_T1": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "accidents",
        "min_utility": 21000000,
        "max_transactions": None,
    },

    # 7
    "hui_ecommerce_T4": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "ecommerce",
        "min_utility": 180000,
        "max_transactions": None,
    },

    # 8
    "hui_ecommerce_60": {
        "algorithm": "hui_miner",
        "algorithm_file": "/work/hui_miner.py",
        "dataset": "ecommerce",
        "min_utility": 180000,
        "max_transactions": 8985,
    },
}


def run(case_id):
    c = CASES[case_id]

    alg = c["algorithm"]
    ds = c["dataset"]
    mu = c["min_utility"]
    n = c["max_transactions"]

    outfile = OUT / f"{case_id}.json"

    cmd = [
        sys.executable,
        "/work/run_baseline_huim.py",
        "--worker",
        "--algorithm", alg,
        "--algorithm-file", c["algorithm_file"],
        "--dataset", ds,
        "--file", f"/work/datasets/{ds}.txt",
        "--min-utility", str(mu),
        "--sample-interval", "0.05",
        "--max-unique-items-unsafe", "22",
    ]

    if n is not None:
        cmd += ["--max-transactions", str(n)]

    started = datetime.now(timezone.utc)

    try:
        cp = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=129600,
            check=False,
        )

        result = None

        for line in reversed(cp.stdout.splitlines()):
            try:
                result = json.loads(line)
                break
            except Exception:
                pass

        if result is None:
            result = {
                "status": "error",
                "error": "No parseable worker JSON",
            }

        if cp.returncode != 0 and result.get("status") == "ok":
            result["status"] = "error"
            result["error"] = cp.stderr[-4000:]

    except subprocess.TimeoutExpired:
        result = {
            "algorithm": alg,
            "dataset": ds,
            "min_utility": mu,
            "max_transactions": n,
            "status": "timeout",
            "error": "Timeout after 129600 seconds",
        }

    payload = {
        "case_id": case_id,
        "algorithm": alg,
        "dataset": ds,
        "min_utility": mu,
        "max_transactions": n,
        "started_utc": started.isoformat(),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "result": result,
    }

    tmp = OUT / f"{case_id}.json.tmp"

    tmp.write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    tmp.replace(outfile)

    print(
        f"{case_id} "
        f"status={result.get('status')} "
        f"runtime={result.get('runtime_ms')} "
        f"peak={result.get('peak_memory_mb')} "
        f"patterns={result.get('pattern_count')}",
        flush=True,
    )


parser = argparse.ArgumentParser()
parser.add_argument("--case", required=True, choices=CASES.keys())
args = parser.parse_args()

run(args.case)
