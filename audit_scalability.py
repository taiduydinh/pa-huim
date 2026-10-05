import csv
from pathlib import Path
from collections import defaultdict

ROOT = Path("/work")

ALGS = [
    "efim", "fhm", "hui_miner",
    "ulb_miner", "upgrowthplus", "d2hup"
]

DATASETS = [
    "foodmart", "ecommerce", "retail", "fruithut",
    "accidents", "kosarak", "chainstore", "chicago_crimes"
]

FRACTIONS = [0.20, 0.40, 0.60, 0.80, 1.00]

# ------------------------------------------------------------
# PA-HUIM reference
# ------------------------------------------------------------
pa = {}

pa_file = ROOT / "pa_huim_results/pa_huim_scalability_results.csv"

with pa_file.open(newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):

        ds = r.get("dataset", "")
        if ds not in DATASETS:
            continue

        if r.get("status") != "ok":
            continue

        try:
            frac = round(float(r["size_fraction"]), 2)
            mu = int(float(r["min_utility"]))

            n_raw = (
                r.get("max_transactions")
                or r.get("read_transactions")
            )
            n = int(float(n_raw))

            patterns = int(float(r["pattern_count"]))
        except Exception:
            continue

        pa[(ds, frac)] = {
            "mu": mu,
            "n": n,
            "patterns": patterns,
        }

# ------------------------------------------------------------
# Gather every baseline scalability CSV
# ------------------------------------------------------------
observed = defaultdict(list)
files_seen = []

for path in ROOT.rglob("baseline_huim_scalability_results.csv"):

    if "pa_huim_results" in str(path):
        continue

    files_seen.append(path)

    try:
        with path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):

                alg = r.get("algorithm", "")
                ds = r.get("dataset", "")

                if alg not in ALGS or ds not in DATASETS:
                    continue

                try:
                    frac = round(float(r["size_fraction"]), 2)
                except Exception:
                    continue

                observed[(alg, ds, frac)].append((r, path))

    except Exception as e:
        print(f"WARNING reading {path}: {e}")

# ------------------------------------------------------------
# Classify
# ------------------------------------------------------------
summary = {
    alg: {
        "correct": 0,
        "timeout": 0,
        "skipped": 0,
        "incorrect": 0,
        "pending": 0,
    }
    for alg in ALGS
}

detail = {}
problems = []

for alg in ALGS:
    for ds in DATASETS:
        for frac in FRACTIONS:

            rows = observed.get((alg, ds, frac), [])
            ref = pa.get((ds, frac))

            correct = None
            timeout = None
            skipped = None
            incorrect = []

            for r, path in rows:

                status = r.get("status", "")

                if status == "ok":

                    try:
                        mu = int(float(r["min_utility"]))
                        n = int(float(r["max_transactions"]))
                        patterns = int(float(r["pattern_count"]))
                    except Exception:
                        incorrect.append((r, path))
                        continue

                    if (
                        ref is not None
                        and mu == ref["mu"]
                        and n == ref["n"]
                        and patterns == ref["patterns"]
                    ):
                        correct = (r, path)
                    else:
                        incorrect.append((r, path))

                elif status == "timeout":
                    timeout = (r, path)

                elif status == "skipped_after_timeout":
                    skipped = (r, path)

            # A valid duplicate always wins over stale/invalid copies.
            if correct:
                state = "correct"
                summary[alg]["correct"] += 1

            elif timeout:
                state = "timeout"
                summary[alg]["timeout"] += 1

            elif skipped:
                state = "skipped"
                summary[alg]["skipped"] += 1

            elif incorrect:
                state = "incorrect"
                summary[alg]["incorrect"] += 1

                r, path = incorrect[-1]

                problems.append({
                    "algorithm": alg,
                    "dataset": ds,
                    "fraction": frac,
                    "expected": ref,
                    "actual": {
                        "min_utility": r.get("min_utility"),
                        "max_transactions": r.get("max_transactions"),
                        "pattern_count": r.get("pattern_count"),
                    },
                    "file": str(path),
                })

            else:
                state = "pending"
                summary[alg]["pending"] += 1

            detail[(alg, ds, frac)] = state

# ------------------------------------------------------------
# Main summary
# ------------------------------------------------------------
print("=" * 108)
print("BDA8 SCALABILITY CORRECTNESS AUDIT")
print("=" * 108)

for alg in ALGS:

    s = summary[alg]

    print(
        f"{alg:14s} "
        f"correct={s['correct']:2d}/40  "
        f"timeout={s['timeout']:2d}  "
        f"skipped={s['skipped']:2d}  "
        f"incorrect={s['incorrect']:2d}  "
        f"pending={s['pending']:2d}"
    )

tot = {
    k: sum(summary[a][k] for a in ALGS)
    for k in summary[ALGS[0]]
}

print("-" * 108)

print(
    f"TOTAL "
    f"correct={tot['correct']}/240  "
    f"timeout={tot['timeout']}  "
    f"skipped={tot['skipped']}  "
    f"incorrect={tot['incorrect']}  "
    f"pending={tot['pending']}"
)

# ------------------------------------------------------------
# Pending detail
# ------------------------------------------------------------
print()
print("=" * 108)
print("PENDING SCALABILITY CASES")
print("=" * 108)

for alg in ALGS:

    lines = []

    for ds in DATASETS:

        pending = [
            frac
            for frac in FRACTIONS
            if detail[(alg, ds, frac)] == "pending"
        ]

        if pending:
            lines.append(
                f"  {ds:18s}: "
                + " ".join(f"{int(x*100):3d}%" for x in pending)
            )

    if lines:
        print()
        print(alg)

        for line in lines:
            print(line)

# ------------------------------------------------------------
# Combined baseline status
# ------------------------------------------------------------
NORMAL_CORRECT = 429
NORMAL_TIMEOUT = 4
NORMAL_SKIPPED = 15
NORMAL_PENDING = 32

combined_correct = NORMAL_CORRECT + tot["correct"]
combined_pending = NORMAL_PENDING + tot["pending"]

print()
print("=" * 108)
print("COMBINED BASELINE STATUS")
print("=" * 108)

print(f"Normal correct:       {NORMAL_CORRECT}/480")
print(f"Scalability correct:  {tot['correct']}/240")
print("-" * 45)

print(
    f"Combined correct:     "
    f"{combined_correct}/720 "
    f"({100*combined_correct/720:.1f}%)"
)

print(
    f"Combined pending:     "
    f"{combined_pending}/720"
)

print(
    f"Including PA-HUIM:    "
    f"{combined_correct + 120}/840 "
    f"({100*(combined_correct + 120)/840:.1f}%) correct"
)

print()
print(f"Scalability result CSV files examined: {len(files_seen)}")

if problems:
    print()
    print("=" * 108)
    print("INCORRECT RESULTS")
    print("=" * 108)

    for p in problems:
        print(p)

else:
    print()
    print("No incorrect scalability results detected.")
