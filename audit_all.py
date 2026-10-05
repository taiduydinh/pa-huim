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

# ============================================================
# PA-HUIM THRESHOLD REFERENCE
# ============================================================

pa_thr = {}

with (ROOT / "pa_huim_results/pa_huim_threshold_results.csv").open(
    newline="", encoding="utf-8"
) as f:
    for r in csv.DictReader(f):

        if r.get("dataset") not in DATASETS:
            continue
        if r.get("status") != "ok":
            continue

        try:
            t = int(float(r["threshold_index"]))
            mu = int(float(r["min_utility"]))
            patterns = int(float(r["pattern_count"]))
        except Exception:
            continue

        pa_thr[(r["dataset"], t)] = {
            "mu": mu,
            "patterns": patterns
        }

# ============================================================
# ALL NORMAL / THRESHOLD RESULTS
# ============================================================

thr_obs = defaultdict(list)

for path in ROOT.rglob("baseline_huim_threshold_results.csv"):

    if "pa_huim_results" in str(path):
        continue

    try:
        with path.open(newline="", encoding="utf-8") as f:

            for r in csv.DictReader(f):

                alg = r.get("algorithm", "")
                ds = r.get("dataset", "")

                if alg not in ALGS or ds not in DATASETS:
                    continue

                try:
                    t = int(float(r["threshold_index"]))
                except Exception:
                    continue

                thr_obs[(alg, ds, t)].append((r, path))

    except Exception:
        pass


thr_summary = {
    a: {
        "correct": 0,
        "timeout": 0,
        "skipped": 0,
        "incorrect": 0,
        "pending": 0
    }
    for a in ALGS
}

thr_detail = {}

for alg in ALGS:

    for ds in DATASETS:

        timeout_indices = set()

        for t in range(10, 0, -1):
            for r, _ in thr_obs.get((alg, ds, t), []):
                if r.get("status") == "timeout":
                    timeout_indices.add(t)

        for t in range(10, 0, -1):

            ref = pa_thr.get((ds, t))
            rows = thr_obs.get((alg, ds, t), [])

            correct = False
            timeout = False
            skipped = False
            bad = False

            for r, _ in rows:

                status = r.get("status", "")

                if status == "timeout":
                    timeout = True
                    continue

                if status == "skipped_after_timeout":
                    skipped = True
                    continue

                if status != "ok":
                    continue

                try:
                    mu = int(float(r["min_utility"]))
                    patterns = int(float(r["pattern_count"]))
                except Exception:
                    bad = True
                    continue

                if (
                    ref is not None
                    and mu == ref["mu"]
                    and patterns == ref["patterns"]
                ):
                    correct = True
                else:
                    bad = True

            if correct:
                state = "correct"

            elif timeout:
                state = "timeout"

            elif skipped:
                state = "skipped"

            elif any(x > t for x in timeout_indices):
                # Conceptual early-stop:
                # lower thresholds after a timeout are skipped.
                state = "skipped"

            elif bad:
                state = "incorrect"

            else:
                state = "pending"

            thr_summary[alg][state] += 1
            thr_detail[(alg, ds, t)] = state


# ============================================================
# PA-HUIM SCALABILITY REFERENCE
# ============================================================

pa_scal = {}

with (ROOT / "pa_huim_results/pa_huim_scalability_results.csv").open(
    newline="", encoding="utf-8"
) as f:

    for r in csv.DictReader(f):

        if r.get("dataset") not in DATASETS:
            continue
        if r.get("status") != "ok":
            continue

        try:
            frac = round(float(r["size_fraction"]), 2)
            mu = int(float(r["min_utility"]))

            nraw = (
                r.get("max_transactions")
                or r.get("read_transactions")
            )

            n = int(float(nraw))
            patterns = int(float(r["pattern_count"]))

        except Exception:
            continue

        pa_scal[(r["dataset"], frac)] = {
            "mu": mu,
            "n": n,
            "patterns": patterns
        }


# ============================================================
# ALL SCALABILITY RESULTS
# ============================================================

scal_obs = defaultdict(list)

for path in ROOT.rglob("baseline_huim_scalability_results.csv"):

    if "pa_huim_results" in str(path):
        continue

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

                scal_obs[(alg, ds, frac)].append((r, path))

    except Exception:
        pass


scal_summary = {
    a: {
        "correct": 0,
        "timeout": 0,
        "skipped": 0,
        "incorrect": 0,
        "pending": 0
    }
    for a in ALGS
}

scal_detail = {}

for alg in ALGS:

    for ds in DATASETS:

        timeout_fracs = set()

        for frac in FRACTIONS:
            for r, _ in scal_obs.get((alg, ds, frac), []):
                if r.get("status") == "timeout":
                    timeout_fracs.add(frac)

        for frac in FRACTIONS:

            ref = pa_scal.get((ds, frac))
            rows = scal_obs.get((alg, ds, frac), [])

            correct = False
            timeout = False
            skipped = False
            bad = False

            for r, _ in rows:

                status = r.get("status", "")

                if status == "timeout":
                    timeout = True
                    continue

                if status == "skipped_after_timeout":
                    skipped = True
                    continue

                if status != "ok":
                    continue

                try:
                    mu = int(float(r["min_utility"]))
                    n = int(float(r["max_transactions"]))
                    patterns = int(float(r["pattern_count"]))
                except Exception:
                    bad = True
                    continue

                if (
                    ref is not None
                    and mu == ref["mu"]
                    and n == ref["n"]
                    and patterns == ref["patterns"]
                ):
                    correct = True
                else:
                    bad = True

            if correct:
                state = "correct"

            elif timeout:
                state = "timeout"

            elif skipped:
                state = "skipped"

            elif any(x < frac for x in timeout_fracs):
                state = "skipped"

            elif bad:
                state = "incorrect"

            else:
                state = "pending"

            scal_summary[alg][state] += 1
            scal_detail[(alg, ds, frac)] = state


# ============================================================
# OUTPUT
# ============================================================

print("=" * 110)
print("NORMAL / THRESHOLD")
print("=" * 110)

for alg in ALGS:

    s = thr_summary[alg]

    print(
        f"{alg:14s} "
        f"correct={s['correct']:3d}/80  "
        f"timeout={s['timeout']:2d}  "
        f"skipped={s['skipped']:2d}  "
        f"incorrect={s['incorrect']:2d}  "
        f"pending={s['pending']:2d}"
    )

TN = {
    k: sum(thr_summary[a][k] for a in ALGS)
    for k in thr_summary[ALGS[0]]
}

print("-" * 110)

print(
    f"TOTAL          "
    f"correct={TN['correct']}/480  "
    f"timeout={TN['timeout']}  "
    f"skipped={TN['skipped']}  "
    f"incorrect={TN['incorrect']}  "
    f"pending={TN['pending']}"
)


print()
print("=" * 110)
print("SCALABILITY")
print("=" * 110)

for alg in ALGS:

    s = scal_summary[alg]

    print(
        f"{alg:14s} "
        f"correct={s['correct']:2d}/40  "
        f"timeout={s['timeout']:2d}  "
        f"skipped={s['skipped']:2d}  "
        f"incorrect={s['incorrect']:2d}  "
        f"pending={s['pending']:2d}"
    )

TS = {
    k: sum(scal_summary[a][k] for a in ALGS)
    for k in scal_summary[ALGS[0]]
}

print("-" * 110)

print(
    f"TOTAL          "
    f"correct={TS['correct']}/240  "
    f"timeout={TS['timeout']}  "
    f"skipped={TS['skipped']}  "
    f"incorrect={TS['incorrect']}  "
    f"pending={TS['pending']}"
)


# ============================================================
# COMBINED
# ============================================================

correct = TN["correct"] + TS["correct"]
timeout = TN["timeout"] + TS["timeout"]
skipped = TN["skipped"] + TS["skipped"]
incorrect = TN["incorrect"] + TS["incorrect"]
pending = TN["pending"] + TS["pending"]

resolved = correct + timeout + skipped + incorrect

print()
print("=" * 110)
print("COMBINED SIX BASELINES")
print("=" * 110)

print(f"Correct:                  {correct:3d} / 720")
print(f"Timeout:                  {timeout:3d}")
print(f"Skipped after timeout:    {skipped:3d}")
print(f"Incorrect:                {incorrect:3d}")
print(f"Pending:                  {pending:3d}")
print(f"Resolved:                 {resolved:3d} / 720")
print()
print(f"Correct rate:             {100*correct/720:.1f}%")
print(f"Resolved rate:            {100*resolved/720:.1f}%")


# ============================================================
# INCLUDE PA-HUIM
# ============================================================

all_correct = correct + 120
all_resolved = resolved + 120

print()
print("=" * 110)
print("INCLUDING PA-HUIM")
print("=" * 110)

print(
    f"Correct experiments:      "
    f"{all_correct} / 840 "
    f"({100*all_correct/840:.1f}%)"
)

print(
    f"Resolved experiments:     "
    f"{all_resolved} / 840 "
    f"({100*all_resolved/840:.1f}%)"
)

print(
    f"Still pending:            "
    f"{pending} / 840"
)


# ============================================================
# PENDING DETAILS
# ============================================================

print()
print("=" * 110)
print("PENDING NORMAL")
print("=" * 110)

for alg in ALGS:
    for ds in DATASETS:

        p = [
            f"T{t}"
            for t in range(10, 0, -1)
            if thr_detail[(alg, ds, t)] == "pending"
        ]

        if p:
            print(
                f"{alg:14s} {ds:18s} "
                + " ".join(p)
            )


print()
print("=" * 110)
print("PENDING SCALABILITY")
print("=" * 110)

for alg in ALGS:
    for ds in DATASETS:

        p = [
            f"{int(frac*100)}%"
            for frac in FRACTIONS
            if scal_detail[(alg, ds, frac)] == "pending"
        ]

        if p:
            print(
                f"{alg:14s} {ds:18s} "
                + " ".join(p)
            )

