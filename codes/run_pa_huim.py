from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import subprocess
import sys
import threading
import time
from array import array
from bisect import bisect_left
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import psutil
except ImportError:
    psutil = None


DATASET_FILES = {
    "foodmart": "foodmart.txt",
    "chainstore": "chainstore.txt",
    "ecommerce": "ecommerce.txt",
    "fruithut": "fruithut.txt",
    "liquor": "liquor.txt",
    "chicago_crimes": "chicago_crimes.txt",
    "yoochoose_buys": "yoochoose_buys.dat",
    "kosarak": "kosarak.txt",
    "accidents": "accidents.txt",
    "retail": "retail.txt",
}

CENTRAL_PERCENTAGES = {
    "foodmart": 0.10,
    "chainstore": 0.005,
    "ecommerce": 0.03,
    "fruithut": 0.02,
    "liquor": 0.05,
    "chicago_crimes": 0.20,
    "yoochoose_buys": 0.01,
    "kosarak": 0.02,
    "accidents": 1.00,
    "retail": 0.02,
}

MIN_UTIL_THRESHOLDS = {
    "foodmart": [3000, 4000, 6000, 7000, 8000, 9000, 12000, 15000, 18000, 24000],
    "chainstore": [90000, 95000, 98000, 130000, 163000, 196000, 261000, 391000, 522000, 652000],
    "ecommerce": [165000, 170000, 175000, 180000, 186000, 224000, 298000, 447000, 596000, 746000],
    "fruithut": [13000, 26000, 39000, 52000, 65000, 79000, 105000, 157000, 209000, 262000],
    "liquor": [2800, 5600, 8400, 11000, 14000, 17000, 22000, 34000, 45000, 56000],
    "chicago_crimes": [4000, 8000, 12000, 16000, 20000, 24000, 32000, 48000, 64000, 79000],
    "yoochoose_buys": [204000, 250000, 260000, 270000, 280000, 290000, 300000, 305000, 407000, 509000],
    "kosarak": [2000000, 2250000, 2500000, 2750000, 3000000, 3250000, 3500000, 4000000, 4500000, 5000000],
    "accidents": [21000000, 22000000, 23000000, 24000000, 25000000, 26000000, 27000000, 28000000, 29000000, 30000000],
    "retail": [1500, 2200, 3000, 3700, 4500, 5300, 6100, 6900, 7700, 8900],
}

SCALABILITY_FRACTIONS = [0.20, 0.40, 0.60, 0.80, 1.00]


class PeakMemorySampler:
    def __init__(self, interval_seconds: float = 0.05):
        if psutil is None:
            raise RuntimeError("psutil is required. Install it with: pip install psutil")
        self.interval_seconds = interval_seconds
        self.process = psutil.Process(os.getpid())
        self.baseline_bytes = 0
        self.peak_bytes = 0
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def __enter__(self):
        self.baseline_bytes = self._rss()
        self.peak_bytes = self.baseline_bytes
        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.peak_bytes = max(self.peak_bytes, self._rss())

    def _rss(self) -> int:
        return int(self.process.memory_info().rss)

    def _sample_loop(self) -> None:
        while self._running:
            self.peak_bytes = max(self.peak_bytes, self._rss())
            time.sleep(self.interval_seconds)

    @property
    def baseline_mb(self) -> float:
        return self.baseline_bytes / 1024.0 / 1024.0

    @property
    def peak_mb(self) -> float:
        return self.peak_bytes / 1024.0 / 1024.0

    @property
    def delta_mb(self) -> float:
        return max(0.0, self.peak_mb - self.baseline_mb)


class PAHUIM:
    def __init__(
        self,
        min_utility: int,
        store_patterns: bool = False,
        max_patterns: Optional[int] = None,
    ):
        if min_utility <= 0:
            raise ValueError("min_utility must be positive.")

        self.min_utility = int(min_utility)
        self.store_patterns = bool(store_patterns)
        self.max_patterns = max_patterns

        self.trans_start = array("q")
        self.trans_end = array("q")
        self.items = array("i")
        self.utils = array("q")
        self.suffix_utils = array("q")

        self.id_to_item: List[int] = []
        self.item_to_id: Dict[int, int] = {}

        self.patterns: List[Tuple[Tuple[int, ...], int]] = []
        self.pattern_count = 0
        self.candidate_count = 0
        self.nodes_visited = 0
        self.promising_item_count = 0
        self.transaction_count = 0
        self.total_utility = 0
        self.database_entry_count = 0

        self._cand_util: List[int] = []
        self._cand_ub: List[int] = []
        self._cand_mark: List[bool] = []
        self._touched: List[int] = []

    def fit_from_spmf_file(
        self,
        path: Path,
        max_transactions: Optional[int] = None,
    ) -> "PAHUIM":
        twu: Dict[int, int] = {}
        total_utility = 0
        transaction_count = 0
        database_entry_count = 0

        for items, utilities, transaction_utility in iter_spmf_utility_transactions(path, max_transactions):
            total_utility += transaction_utility
            transaction_count += 1
            database_entry_count += len(items)

            seen = set()
            for item in items:
                if item not in seen:
                    twu[item] = twu.get(item, 0) + transaction_utility
                    seen.add(item)

        promising_items = [item for item, value in twu.items() if value >= self.min_utility]
        promising_items.sort(key=lambda item: (twu[item], item))

        self.item_to_id = {item: idx for idx, item in enumerate(promising_items)}
        self.id_to_item = promising_items[:]
        self.promising_item_count = len(promising_items)
        self.transaction_count = transaction_count
        self.total_utility = total_utility
        self.database_entry_count = database_entry_count

        self._build_global_arrays_from_file(path, max_transactions)

        n_items = len(self.id_to_item)
        self._cand_util = [0] * n_items
        self._cand_ub = [0] * n_items
        self._cand_mark = [False] * n_items
        self._touched = []

        return self

    def mine(self) -> None:
        self.patterns = []
        self.pattern_count = 0
        self.candidate_count = 0
        self.nodes_visited = 0

        root_tid: List[int] = []
        root_pos: List[int] = []
        root_pu: List[int] = []

        for tid in range(len(self.trans_start)):
            if self.trans_start[tid] < self.trans_end[tid]:
                root_tid.append(tid)
                root_pos.append(self.trans_start[tid] - 1)
                root_pu.append(0)

        self._search([], root_tid, root_pos, root_pu)

    def _build_global_arrays_from_file(
        self,
        path: Path,
        max_transactions: Optional[int],
    ) -> None:
        self.trans_start = array("q")
        self.trans_end = array("q")
        self.items = array("i")
        self.utils = array("q")
        self.suffix_utils = array("q")

        for raw_items, raw_utils, _ in iter_spmf_utility_transactions(path, max_transactions):
            merged: Dict[int, int] = {}

            for item, utility in zip(raw_items, raw_utils):
                if utility <= 0:
                    continue
                item_id = self.item_to_id.get(item)
                if item_id is not None:
                    merged[item_id] = merged.get(item_id, 0) + int(utility)

            filtered = sorted(merged.items(), key=lambda pair: pair[0])

            start = len(self.items)
            self.trans_start.append(start)

            for item_id, utility in filtered:
                self.items.append(item_id)
                self.utils.append(utility)
                self.suffix_utils.append(0)

            end = len(self.items)
            self.trans_end.append(end)

            running_sum = 0
            for pos in range(end - 1, start - 1, -1):
                self.suffix_utils[pos] = running_sum
                running_sum += self.utils[pos]

    def _search(
        self,
        prefix: List[int],
        proj_tid: List[int],
        proj_pos: List[int],
        proj_pu: List[int],
    ) -> None:
        if not proj_tid:
            return

        self.nodes_visited += 1
        candidates = self._collect_candidates(proj_tid, proj_pos, proj_pu)
        self.candidate_count += len(candidates)

        for item_id, exact_utility, upper_bound in candidates:
            new_prefix = prefix + [item_id]

            if exact_utility >= self.min_utility:
                self._save_pattern(new_prefix, exact_utility)
                if self.max_patterns is not None and self.pattern_count >= self.max_patterns:
                    return

            if upper_bound >= self.min_utility:
                child_tid, child_pos, child_pu = self._project(
                    item_id=item_id,
                    proj_tid=proj_tid,
                    proj_pos=proj_pos,
                    proj_pu=proj_pu,
                )
                self._search(new_prefix, child_tid, child_pos, child_pu)

                if self.max_patterns is not None and self.pattern_count >= self.max_patterns:
                    return

    def _collect_candidates(
        self,
        proj_tid: List[int],
        proj_pos: List[int],
        proj_pu: List[int],
    ) -> List[Tuple[int, int, int]]:
        touched = self._touched
        cand_util = self._cand_util
        cand_ub = self._cand_ub
        cand_mark = self._cand_mark
        touched.clear()

        for row in range(len(proj_tid)):
            tid = proj_tid[row]
            start = proj_pos[row] + 1
            end = self.trans_end[tid]
            prefix_utility = proj_pu[row]

            for pos in range(start, end):
                item_id = self.items[pos]

                if not cand_mark[item_id]:
                    cand_mark[item_id] = True
                    touched.append(item_id)

                utility_with_item = prefix_utility + self.utils[pos]
                cand_util[item_id] += utility_with_item
                cand_ub[item_id] += utility_with_item + self.suffix_utils[pos]

        candidates: List[Tuple[int, int, int]] = []
        touched.sort()

        for item_id in touched:
            candidates.append((item_id, cand_util[item_id], cand_ub[item_id]))
            cand_util[item_id] = 0
            cand_ub[item_id] = 0
            cand_mark[item_id] = False

        return candidates

    def _project(
        self,
        item_id: int,
        proj_tid: List[int],
        proj_pos: List[int],
        proj_pu: List[int],
    ) -> Tuple[List[int], List[int], List[int]]:
        child_tid: List[int] = []
        child_pos: List[int] = []
        child_pu: List[int] = []

        items = self.items
        utils = self.utils
        trans_end = self.trans_end

        for row in range(len(proj_tid)):
            tid = proj_tid[row]
            start = proj_pos[row] + 1
            end = trans_end[tid]
            pos = bisect_left(items, item_id, start, end)

            if pos < end and items[pos] == item_id:
                child_tid.append(tid)
                child_pos.append(pos)
                child_pu.append(proj_pu[row] + utils[pos])

        return child_tid, child_pos, child_pu

    def _save_pattern(self, prefix: List[int], utility: int) -> None:
        self.pattern_count += 1
        if self.store_patterns:
            pattern = tuple(self.id_to_item[item_id] for item_id in prefix)
            self.patterns.append((pattern, utility))


def iter_spmf_utility_transactions(
    path: Path,
    max_transactions: Optional[int] = None,
) -> Iterable[Tuple[List[int], List[int], int]]:
    count = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()

            if not line or line.startswith("#") or line.startswith("%") or line.startswith("@"):
                continue

            parts = line.split(":")

            items = [int(x) for x in parts[0].split()]

            if len(parts) >= 3:
                transaction_utility = int(float(parts[1].strip()))
                utilities = [int(float(x)) for x in parts[2].split()]
            elif len(parts) == 2:
                utilities = [int(float(x)) for x in parts[1].split()]
                transaction_utility = sum(utilities)
            else:
                raise ValueError(f"Bad SPMF utility format at line {line_no}: {line[:120]}")

            if len(items) != len(utilities):
                raise ValueError(
                    f"Item/utility length mismatch at line {line_no}: "
                    f"{len(items)} items vs {len(utilities)} utilities"
                )

            yield items, utilities, transaction_utility

            count += 1
            if max_transactions is not None and count >= max_transactions:
                break


def scan_dataset_stats(path: Path) -> Dict[str, int]:
    transaction_count = 0
    total_utility = 0
    entry_count = 0
    unique_items = set()

    for items, utilities, transaction_utility in iter_spmf_utility_transactions(path):
        transaction_count += 1
        total_utility += transaction_utility
        entry_count += len(items)
        unique_items.update(items)

    return {
        "transaction_count": transaction_count,
        "total_utility": total_utility,
        "entry_count": entry_count,
        "unique_item_count": len(unique_items),
    }


def scan_subset_total_utility(path: Path, max_transactions: int) -> Dict[str, int]:
    transaction_count = 0
    total_utility = 0
    entry_count = 0

    for items, utilities, transaction_utility in iter_spmf_utility_transactions(path, max_transactions):
        transaction_count += 1
        total_utility += transaction_utility
        entry_count += len(items)

    return {
        "transaction_count": transaction_count,
        "total_utility": total_utility,
        "entry_count": entry_count,
    }


def round_min_utility(value: float) -> int:
    if value < 10000:
        base = 100
    elif value < 1000000:
        base = 1000
    else:
        base = 10000

    rounded = int(round(value / base) * base)
    return max(1, rounded)


def find_dataset_file(data_dir: Path, dataset_name: str) -> Path:
    expected = DATASET_FILES[dataset_name]
    candidates = [
        data_dir / expected,
        data_dir / dataset_name,
        data_dir / f"{dataset_name}.txt",
        data_dir / f"{dataset_name}.dat",
    ]

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    matches = sorted(data_dir.glob(dataset_name + ".*"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Cannot find dataset file for {dataset_name} in {data_dir}")


def run_worker(args: argparse.Namespace) -> None:
    path = Path(args.file).resolve()
    result = {
        "dataset": args.dataset,
        "file": str(path),
        "min_utility": int(args.min_utility),
        "max_transactions": args.max_transactions,
        "status": "ok",
        "error": "",
    }

    try:
        gc.collect()

        with PeakMemorySampler(args.sample_interval) as memory:
            start = time.perf_counter()

            miner = PAHUIM(
                min_utility=int(args.min_utility),
                store_patterns=bool(args.store_patterns),
                max_patterns=args.max_patterns,
            )
            miner.fit_from_spmf_file(path, args.max_transactions)
            miner.mine()

            end = time.perf_counter()

        result.update({
            "runtime_ms": round((end - start) * 1000.0, 3),
            "baseline_memory_mb": round(memory.baseline_mb, 3),
            "peak_memory_mb": round(memory.peak_mb, 3),
            "delta_memory_mb": round(memory.delta_mb, 3),
            "pattern_count": miner.pattern_count,
            "candidate_count": miner.candidate_count,
            "nodes_visited": miner.nodes_visited,
            "promising_item_count": miner.promising_item_count,
            "read_transactions": miner.transaction_count,
            "read_total_utility": miner.total_utility,
            "read_entries": miner.database_entry_count,
            "array_transactions": len(miner.trans_start),
            "array_entries": len(miner.items),
        })

    except Exception as exc:
        result["status"] = "error"
        result["error"] = repr(exc)

    print(json.dumps(result, ensure_ascii=False))


def run_one_subprocess(
    script_path: Path,
    dataset: str,
    file_path: Path,
    min_utility: int,
    max_transactions: Optional[int],
    timeout_sec: Optional[int],
    sample_interval: float,
    store_patterns: bool,
    max_patterns: Optional[int],
) -> Dict[str, object]:
    cmd = [
        sys.executable,
        str(script_path),
        "--worker",
        "--dataset", dataset,
        "--file", str(file_path),
        "--min-utility", str(min_utility),
        "--sample-interval", str(sample_interval),
    ]

    if max_transactions is not None:
        cmd.extend(["--max-transactions", str(max_transactions)])

    if store_patterns:
        cmd.append("--store-patterns")

    if max_patterns is not None:
        cmd.extend(["--max-patterns", str(max_patterns)])

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
        )

        stdout = completed.stdout.strip().splitlines()
        if not stdout:
            return {
                "dataset": dataset,
                "file": str(file_path),
                "min_utility": min_utility,
                "max_transactions": max_transactions,
                "status": "error",
                "error": completed.stderr.strip() or "Worker produced no output.",
            }

        result = json.loads(stdout[-1])
        if completed.returncode != 0 and result.get("status") == "ok":
            result["status"] = "error"
            result["error"] = completed.stderr.strip()
        return result

    except subprocess.TimeoutExpired:
        return {
            "dataset": dataset,
            "file": str(file_path),
            "min_utility": min_utility,
            "max_transactions": max_transactions,
            "status": "timeout",
            "error": f"Timeout after {timeout_sec} seconds.",
        }


def append_csv_row(path: Path, row: Dict[str, object], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_completed_keys(path: Path, key_fields: Sequence[str]) -> set:
    if not path.exists():
        return set()

    keys = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add(tuple(row.get(field, "") for field in key_fields))
    return keys


def write_dataset_summary(summary_path: Path, rows: List[Dict[str, object]]) -> None:
    fieldnames = [
        "dataset", "file", "transaction_count", "total_utility",
        "entry_count", "unique_item_count", "central_percentage",
        "central_min_utility"
    ]
    summary_path.parent.mkdir(parents=True, exist_ok=True)

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_result_fieldnames() -> List[str]:
    return [
        "experiment",
        "dataset",
        "file",
        "threshold_index",
        "size_fraction",
        "max_transactions",
        "min_utility",
        "central_percentage",
        "threshold_mode",
        "runtime_ms",
        "baseline_memory_mb",
        "peak_memory_mb",
        "delta_memory_mb",
        "pattern_count",
        "candidate_count",
        "nodes_visited",
        "promising_item_count",
        "read_transactions",
        "read_total_utility",
        "read_entries",
        "array_transactions",
        "array_entries",
        "status",
        "error",
    ]


def run_master(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    script_path = Path(__file__).resolve()

    selected_datasets = args.datasets or list(DATASET_FILES.keys())
    invalid = [name for name in selected_datasets if name not in DATASET_FILES]
    if invalid:
        raise ValueError(f"Unknown dataset names: {invalid}")

    result_fields = make_result_fieldnames()
    threshold_csv = out_dir / "pa_huim_threshold_results.csv"
    scalability_csv = out_dir / "pa_huim_scalability_results.csv"
    summary_csv = out_dir / "pa_huim_dataset_summary.csv"

    threshold_keys = load_completed_keys(
        threshold_csv,
        ["experiment", "dataset", "threshold_index", "min_utility", "max_transactions"],
    )
    scalability_keys = load_completed_keys(
        scalability_csv,
        ["experiment", "dataset", "size_fraction", "min_utility", "max_transactions"],
    )

    print(f"Data directory: {data_dir}")
    print(f"Output directory: {out_dir}")
    print(f"Datasets: {', '.join(selected_datasets)}")
    print()

    dataset_info: Dict[str, Dict[str, object]] = {}
    summary_rows: List[Dict[str, object]] = []

    for dataset in selected_datasets:
        file_path = find_dataset_file(data_dir, dataset)
        print(f"Scanning {dataset}: {file_path.name}")
        stats = scan_dataset_stats(file_path)
        central_min = MIN_UTIL_THRESHOLDS[dataset][3]

        info = {
            "dataset": dataset,
            "file_path": file_path,
            **stats,
            "central_percentage": CENTRAL_PERCENTAGES[dataset],
            "central_min_utility": central_min,
        }
        dataset_info[dataset] = info

        summary_rows.append({
            "dataset": dataset,
            "file": file_path.name,
            "transaction_count": stats["transaction_count"],
            "total_utility": stats["total_utility"],
            "entry_count": stats["entry_count"],
            "unique_item_count": stats["unique_item_count"],
            "central_percentage": CENTRAL_PERCENTAGES[dataset],
            "central_min_utility": central_min,
        })

    write_dataset_summary(summary_csv, summary_rows)
    print(f"\nWrote dataset summary: {summary_csv}")
    print()

    if args.run_thresholds:
        for dataset in selected_datasets:
            file_path = dataset_info[dataset]["file_path"]
            thresholds = list(MIN_UTIL_THRESHOLDS[dataset])

            if args.high_to_low:
                iterable = list(enumerate(thresholds, start=1))[::-1]
            else:
                iterable = list(enumerate(thresholds, start=1))

            for threshold_index, min_utility in iterable:
                row_key = (
                    "threshold",
                    dataset,
                    str(threshold_index),
                    str(min_utility),
                    "",
                )

                if row_key in threshold_keys and not args.overwrite:
                    print(f"[skip] threshold {dataset} T{threshold_index} minUtil={min_utility}")
                    continue

                print(f"[run ] threshold {dataset} T{threshold_index} minUtil={min_utility}")

                result = run_one_subprocess(
                    script_path=script_path,
                    dataset=dataset,
                    file_path=file_path,
                    min_utility=min_utility,
                    max_transactions=None,
                    timeout_sec=args.timeout_sec,
                    sample_interval=args.sample_interval,
                    store_patterns=args.store_patterns,
                    max_patterns=args.max_patterns,
                )

                row = {
                    "experiment": "threshold",
                    "threshold_index": threshold_index,
                    "size_fraction": "",
                    "central_percentage": CENTRAL_PERCENTAGES[dataset],
                    "threshold_mode": "absolute",
                    **result,
                }
                append_csv_row(threshold_csv, row, result_fields)
                print(f"       status={row['status']} runtime={row.get('runtime_ms', '')} ms "
                      f"peak={row.get('peak_memory_mb', '')} MB patterns={row.get('pattern_count', '')}")

    if args.run_scalability:
        for dataset in selected_datasets:
            info = dataset_info[dataset]
            file_path = info["file_path"]
            transaction_count = int(info["transaction_count"])

            for fraction in args.scalability_fractions:
                max_transactions = max(1, int(round(transaction_count * fraction)))

                if args.scalability_threshold_mode == "percentage":
                    subset_stats = scan_subset_total_utility(file_path, max_transactions)
                    min_utility = round_min_utility(
                        subset_stats["total_utility"] * CENTRAL_PERCENTAGES[dataset] / 100.0
                    )
                else:
                    min_utility = MIN_UTIL_THRESHOLDS[dataset][3]

                row_key = (
                    "scalability",
                    dataset,
                    f"{fraction:.2f}",
                    str(min_utility),
                    str(max_transactions),
                )

                if row_key in scalability_keys and not args.overwrite:
                    print(f"[skip] scalability {dataset} {fraction:.2f} minUtil={min_utility}")
                    continue

                print(
                    f"[run ] scalability {dataset} fraction={fraction:.2f} "
                    f"maxTrans={max_transactions} minUtil={min_utility}"
                )

                result = run_one_subprocess(
                    script_path=script_path,
                    dataset=dataset,
                    file_path=file_path,
                    min_utility=min_utility,
                    max_transactions=max_transactions,
                    timeout_sec=args.timeout_sec,
                    sample_interval=args.sample_interval,
                    store_patterns=args.store_patterns,
                    max_patterns=args.max_patterns,
                )

                row = {
                    "experiment": "scalability",
                    "threshold_index": "",
                    "size_fraction": f"{fraction:.2f}",
                    "central_percentage": CENTRAL_PERCENTAGES[dataset],
                    "threshold_mode": args.scalability_threshold_mode,
                    **result,
                }
                append_csv_row(scalability_csv, row, result_fields)
                print(f"       status={row['status']} runtime={row.get('runtime_ms', '')} ms "
                      f"peak={row.get('peak_memory_mb', '')} MB patterns={row.get('pattern_count', '')}")

    print("\nFinished.")
    print(f"Threshold results:   {threshold_csv}")
    print(f"Scalability results: {scalability_csv}")
    print(f"Dataset summary:     {summary_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=".", help="Folder containing the 10 dataset files.")
    parser.add_argument("--out-dir", default="pa_huim_results", help="Folder for CSV result files.")
    parser.add_argument("--datasets", nargs="*", default=None, help="Optional subset of dataset names.")
    parser.add_argument("--run-thresholds", action="store_true", help="Run threshold experiment.")
    parser.add_argument("--run-scalability", action="store_true", help="Run scalability experiment.")
    parser.add_argument("--high-to-low", action="store_true", default=True, help="Run thresholds from high to low.")
    parser.add_argument("--overwrite", action="store_true", help="Do not skip rows already found in CSV outputs.")
    parser.add_argument("--timeout-sec", type=int, default=None, help="Timeout per run. Default: no timeout.")
    parser.add_argument("--sample-interval", type=float, default=0.05, help="Memory sampling interval in seconds.")
    parser.add_argument("--store-patterns", action="store_true", help="Store discovered patterns in memory. Not recommended for benchmarking.")
    parser.add_argument("--max-patterns", type=int, default=None, help="Stop after this many HUIs. Mainly for debugging.")
    parser.add_argument(
        "--scalability-fractions",
        type=float,
        nargs="*",
        default=SCALABILITY_FRACTIONS,
        help="Dataset-size fractions for scalability experiments.",
    )
    parser.add_argument(
        "--scalability-threshold-mode",
        choices=["percentage", "absolute"],
        default="absolute",
        help="absolute: use one fixed full-dataset central minUtil for all size fractions; percentage: scale minUtil by subset total utility.",
    )

    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--dataset", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--min-utility", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--max-transactions", type=int, default=None, help=argparse.SUPPRESS)

    args = parser.parse_args()

    if not args.run_thresholds and not args.run_scalability and not args.worker:
        args.run_thresholds = True
        args.run_scalability = True

    if args.worker:
        if args.dataset is None or args.file is None or args.min_utility is None:
            parser.error("--worker requires --dataset, --file, and --min-utility")

    return args


if __name__ == "__main__":
    parsed_args = parse_args()

    if parsed_args.worker:
        run_worker(parsed_args)
    else:
        run_master(parsed_args)
