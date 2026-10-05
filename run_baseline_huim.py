from __future__ import annotations

import argparse
import csv
import gc
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from itertools import combinations
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

ALGORITHM_FILES = {
    "efim": "efim.py",
    "fhm": "fhm.py",
    "upgrowthplus": "up_growthplus.py",
    "d2hup": "d2hup.py",
    "hui_miner": "hui_miner.py",
    "ulb_miner": "ulb_miner.py",
}

UNSAFE_BRUTE_FORCE_ALGORITHMS = set()
DEFAULT_ALGORITHMS = ["efim", "fhm", "hui_miner", "ulb_miner", "upgrowthplus", "d2hup"]


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


def iter_spmf_lines(path: Path, max_transactions: Optional[int] = None) -> Iterable[str]:
    count = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "%", "@")):
                continue
            yield line
            count += 1
            if max_transactions is not None and count >= max_transactions:
                break


def iter_spmf_utility_transactions(path: Path, max_transactions: Optional[int] = None):
    """
    Read SPMF utility-format transactions.

    Supports both:
      1) Standard 3-part format: items:TU:itemUtilities
      2) PA-HUIM-compatible 2-part format: items:itemUtilities

    For 2-part input, transaction utility is reconstructed as sum(itemUtilities),
    matching the PA-HUIM parser behavior.
    """
    for line_no, line in enumerate(iter_spmf_lines(path, max_transactions), start=1):
        parts = line.split(":")

        if len(parts) >= 3:
            items = [int(x) for x in parts[0].split()]
            transaction_utility = int(float(parts[1].strip()))
            utilities = [int(float(x)) for x in parts[2].split()]
        elif len(parts) == 2:
            items = [int(x) for x in parts[0].split()]
            utilities = [int(float(x)) for x in parts[1].split()]
            transaction_utility = sum(utilities)
        else:
            raise ValueError(f"Bad SPMF utility format near transaction {line_no}: {line[:120]}")

        if len(items) != len(utilities):
            raise ValueError(
                f"Item/utility mismatch near transaction {line_no}: "
                f"{len(items)} items vs {len(utilities)} utilities."
            )

        yield items, utilities, transaction_utility

def scan_dataset_stats(path: Path, max_transactions: Optional[int] = None) -> Dict[str, int]:
    transaction_count = 0
    total_utility = 0
    entry_count = 0
    unique_items = set()
    for items, _, transaction_utility in iter_spmf_utility_transactions(path, max_transactions):
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


def round_min_utility(value: float) -> int:
    base = 100 if value < 10000 else 1000 if value < 1000000 else 10000
    return max(1, int(round(value / base) * base))


def find_dataset_file(data_dir: Path, dataset_name: str) -> Path:
    expected = DATASET_FILES[dataset_name]
    candidates = [data_dir / expected, data_dir / dataset_name, data_dir / f"{dataset_name}.txt", data_dir / f"{dataset_name}.dat"]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    matches = sorted(data_dir.glob(dataset_name + ".*"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"Cannot find dataset file for {dataset_name} in {data_dir}")


def find_algorithm_file(algo_dir: Path, algorithm: str) -> Path:
    candidates = [algo_dir / ALGORITHM_FILES[algorithm]]
    if algorithm == "hui_miner":
        candidates += [algo_dir / "hui_miner(1).py", algo_dir / "hui_miner.py"]
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    raise FileNotFoundError(f"Cannot find code file for algorithm '{algorithm}' in {algo_dir}.")


def _first_data_line_has_three_parts(input_path: Path) -> bool:
    with input_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "%", "@")):
                continue
            return len(line.split(":")) >= 3
    return True


def make_subset_file(input_path: Path, max_transactions: Optional[int], temp_dir: Path) -> Path:
    """
    Return a worker input file.

    If the original file is already standard 3-part SPMF and no subset is needed,
    use it directly. Otherwise, write a temporary normalized 3-part file.
    """
    needs_normalization = not _first_data_line_has_three_parts(input_path)

    if max_transactions is None and not needs_normalization:
        return input_path

    if max_transactions is None:
        output_path = temp_dir / f"{input_path.stem}_normalized_3part{input_path.suffix or '.txt'}"
    else:
        output_path = temp_dir / f"{input_path.stem}_first_{max_transactions}_normalized_3part{input_path.suffix or '.txt'}"

    with output_path.open("w", encoding="utf-8", newline="\n") as out:
        for items, utilities, transaction_utility in iter_spmf_utility_transactions(input_path, max_transactions):
            out.write(
                " ".join(map(str, items))
                + f":{transaction_utility}:"
                + " ".join(map(str, utilities))
                + "\n"
            )

    return output_path

def count_output_patterns(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return sum(1 for line in f if line.strip())


def import_module_from_file(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_hui_miner_bruteforce(path: Path, min_utility: int, output_path: Path) -> Dict[str, int]:
    transactions = [(items, utilities) for items, utilities, _ in iter_spmf_utility_transactions(path)]
    unique_items = sorted({item for items, _ in transactions for item in items})
    pattern_count = 0
    candidate_count = 0
    with output_path.open("w", encoding="utf-8") as out:
        for size in range(1, len(unique_items) + 1):
            for itemset in combinations(unique_items, size):
                candidate_count += 1
                itemset_set = set(itemset)
                utility = 0
                for items, utilities in transactions:
                    trans_set = set(items)
                    if itemset_set.issubset(trans_set):
                        pos = {item: idx for idx, item in enumerate(items)}
                        utility += sum(utilities[pos[item]] for item in itemset)
                if utility >= min_utility:
                    pattern_count += 1
                    out.write(f"{' '.join(map(str, itemset))} #UTIL: {utility}\n")
    return {"pattern_count": pattern_count, "candidate_count": candidate_count}


def run_algorithm_adapter(algorithm: str, algo_path: Path, input_path: Path, output_path: Path, min_utility: int) -> Dict[str, object]:
    module_name = f"_benchmark_{algorithm}_{os.getpid()}_{int(time.time() * 1000000)}"

    if algorithm == "fhm":
        mod = import_module_from_file(algo_path, module_name)
        algo = mod.AlgoFHM()
        algo.runAlgorithm(str(input_path), str(output_path), int(min_utility))
        return {
            "pattern_count": int(getattr(algo, "huiCount", count_output_patterns(output_path))),
            "candidate_count": int(getattr(algo, "candidateCount", -1)),
            "algorithm_internal_memory_mb": float(mod.MemoryLogger().get_max_memory()),
        }

    if algorithm == "upgrowthplus":
        mod = import_module_from_file(algo_path, module_name)
        algo = mod.AlgoUPGrowthPlus()
        algo.run_algorithm(str(input_path), str(output_path), int(min_utility))
        return {
            "pattern_count": int(getattr(algo, "huiCount", count_output_patterns(output_path))),
            "candidate_count": int(getattr(algo, "phuisCount", -1)),
            "algorithm_internal_memory_mb": float(getattr(algo, "maxMemory", -1.0)),
        }

    if algorithm == "d2hup":
        mod = import_module_from_file(algo_path, module_name)
        algo = mod.AlgoD2HUP()
        if hasattr(algo, "DEBUG"):
            algo.DEBUG = False
        algo.runAlgorithm(str(input_path), str(output_path), int(min_utility))
        return {
            "pattern_count": int(getattr(algo, "huiCount", count_output_patterns(output_path))),
            "candidate_count": -1,
            "case1_count": int(getattr(algo, "case1count", -1)),
            "case2_count": int(getattr(algo, "case2count", -1)),
            "algorithm_internal_memory_mb": float(mod.MemoryLogger.get_instance().get_max_memory()),
        }

    if algorithm == "efim":
        mod = import_module_from_file(algo_path, module_name)
        algo = mod.AlgoEFIM()

        if hasattr(algo, "run_algorithm"):
            algo.run_algorithm(
                min_utility=int(min_utility),
                input_path=str(input_path),
                output_path=str(output_path),
                activate_transaction_merging=True,
                maximum_transaction_count=None,
                activate_subtree_utility_pruning=True,
                write_output=True,
            )
        else:
            algo.runAlgorithm(int(min_utility), str(input_path), str(output_path), True, None, True)

        memory_logger = getattr(mod, "MemoryLogger", None)
        internal_memory = -1.0

        if memory_logger is not None:
            if hasattr(memory_logger, "getInstance"):
                internal_memory = float(memory_logger.getInstance().getMaxMemory())
            elif hasattr(memory_logger, "get_instance"):
                internal_memory = float(memory_logger.get_instance().get_max_memory())

        return {
            "pattern_count": int(getattr(algo, "patternCount", count_output_patterns(output_path))),
            "candidate_count": int(getattr(algo, "candidateCount", -1)),
            "merge_count": int(getattr(algo, "mergeCount", -1)),
            "transaction_reading_count": int(getattr(algo, "transactionReadingCount", -1)),
            "algorithm_internal_memory_mb": internal_memory,
        }

    if algorithm == "hui_miner":
        mod = import_module_from_file(algo_path, module_name)

        if hasattr(mod, "AlgoHUIMiner"):
            algo = mod.AlgoHUIMiner()

            if hasattr(algo, "run_algorithm"):
                algo.run_algorithm(str(input_path), str(output_path), int(min_utility))
            else:
                algo.runAlgorithm(str(input_path), str(output_path), int(min_utility))

            memory_logger = getattr(mod, "MemoryLogger", None)
            internal_memory = -1.0

            if memory_logger is not None:
                if hasattr(memory_logger, "getInstance"):
                    internal_memory = float(memory_logger.getInstance().getMaxMemory())
                elif hasattr(memory_logger, "get_instance"):
                    internal_memory = float(memory_logger.get_instance().get_max_memory())

            return {
                "pattern_count": int(getattr(algo, "huiCount", count_output_patterns(output_path))),
                "candidate_count": int(getattr(algo, "joinCount", getattr(algo, "join_count", -1))),
                "algorithm_internal_memory_mb": internal_memory,
            }

        stats = run_hui_miner_bruteforce(input_path, int(min_utility), output_path)
        return {**stats, "algorithm_internal_memory_mb": -1.0}

    if algorithm == "ulb_miner":
        mod = import_module_from_file(algo_path, module_name)
        class_candidates = ["AlgoULBMiner", "AlgoULB_Miner", "ULBMiner", "AlgoULB"]
        method_candidates = ["runAlgorithm", "run_algorithm", "run"]
        algo = None
        for class_name in class_candidates:
            if hasattr(mod, class_name):
                algo = getattr(mod, class_name)()
                break
        if algo is None:
            raise AttributeError("Could not find a supported ULB-Miner class.")
        for method_name in method_candidates:
            if hasattr(algo, method_name):
                method = getattr(algo, method_name)
                try:
                    method(str(input_path), str(output_path), int(min_utility))
                except TypeError:
                    method(str(input_path), int(min_utility), str(output_path))
                return {
                    "pattern_count": int(getattr(algo, "huiCount", getattr(algo, "pattern_count", count_output_patterns(output_path)))),
                    "candidate_count": int(getattr(algo, "candidateCount", getattr(algo, "candidate_count", -1))),
                    "algorithm_internal_memory_mb": float(getattr(algo, "maxMemory", getattr(algo, "max_memory", -1.0))),
                }
        raise AttributeError("Could not find a supported ULB-Miner run method.")

    raise ValueError(f"Unsupported algorithm: {algorithm}")


def run_worker(args: argparse.Namespace) -> None:
    result = {
        "algorithm": args.algorithm,
        "dataset": args.dataset,
        "file": args.file,
        "algorithm_file": args.algorithm_file,
        "min_utility": int(args.min_utility),
        "max_transactions": args.max_transactions,
        "status": "ok",
        "error": "",
    }
    try:
        input_path = Path(args.file).resolve()
        algo_path = Path(args.algorithm_file).resolve()
        with tempfile.TemporaryDirectory(prefix="huim_benchmark_worker_") as td:
            temp_dir = Path(td)
            working_input = make_subset_file(input_path, args.max_transactions, temp_dir)
            output_path = temp_dir / f"{args.algorithm}_{args.dataset}_{args.min_utility}_output.txt"

            if args.algorithm in UNSAFE_BRUTE_FORCE_ALGORITHMS and not args.include_unsafe:
                result["status"] = "skipped"
                result["error"] = f"{args.algorithm} is marked unsafe because the uploaded code is brute-force-like. Use --include-unsafe only for toy datasets."
                print(json.dumps(result, ensure_ascii=False))
                return

            if args.algorithm in UNSAFE_BRUTE_FORCE_ALGORITHMS and args.max_unique_items_unsafe is not None:
                stats = scan_dataset_stats(working_input)
                if stats["unique_item_count"] > args.max_unique_items_unsafe:
                    result["status"] = "skipped"
                    result["error"] = f"{args.algorithm} skipped: unique_item_count={stats['unique_item_count']} > max_unique_items_unsafe={args.max_unique_items_unsafe}."
                    print(json.dumps(result, ensure_ascii=False))
                    return

            gc.collect()
            with PeakMemorySampler(args.sample_interval) as memory:
                start = time.perf_counter()
                algo_stats = run_algorithm_adapter(args.algorithm, algo_path, working_input, output_path, int(args.min_utility))
                end = time.perf_counter()

            read_stats = scan_dataset_stats(working_input)
            result.update({
                "runtime_ms": round((end - start) * 1000.0, 3),
                "baseline_memory_mb": round(memory.baseline_mb, 3),
                "peak_memory_mb": round(memory.peak_mb, 3),
                "delta_memory_mb": round(memory.delta_mb, 3),
                "output_pattern_lines": count_output_patterns(output_path),
                **algo_stats,
                "read_transactions": read_stats["transaction_count"],
                "read_total_utility": read_stats["total_utility"],
                "read_entries": read_stats["entry_count"],
                "read_unique_items": read_stats["unique_item_count"],
            })
    except Exception as exc:
        result["status"] = "error"
        result["error"] = repr(exc)
    print(json.dumps(result, ensure_ascii=False))


def run_one_subprocess(script_path: Path, algorithm: str, algorithm_file: Path, dataset: str, file_path: Path, min_utility: int, max_transactions: Optional[int], timeout_sec: Optional[int], sample_interval: float, include_unsafe: bool, max_unique_items_unsafe: Optional[int]) -> Dict[str, object]:
    cmd = [sys.executable, str(script_path), "--worker", "--algorithm", algorithm, "--algorithm-file", str(algorithm_file), "--dataset", dataset, "--file", str(file_path), "--min-utility", str(min_utility), "--sample-interval", str(sample_interval)]
    if max_transactions is not None:
        cmd += ["--max-transactions", str(max_transactions)]
    if include_unsafe:
        cmd.append("--include-unsafe")
    if max_unique_items_unsafe is not None:
        cmd += ["--max-unique-items-unsafe", str(max_unique_items_unsafe)]
    try:
        completed = subprocess.run(cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout_sec)
        lines = completed.stdout.strip().splitlines()
        if not lines:
            return {"algorithm": algorithm, "dataset": dataset, "file": str(file_path), "algorithm_file": str(algorithm_file), "min_utility": min_utility, "max_transactions": max_transactions, "status": "error", "error": completed.stderr.strip() or "Worker produced no output."}
        result = json.loads(lines[-1])
        if completed.returncode != 0 and result.get("status") == "ok":
            result["status"] = "error"
            result["error"] = completed.stderr.strip()
        if completed.stderr.strip():
            result["stderr_tail"] = completed.stderr.strip()[-1000:]
        return result
    except subprocess.TimeoutExpired:
        return {"algorithm": algorithm, "dataset": dataset, "file": str(file_path), "algorithm_file": str(algorithm_file), "min_utility": min_utility, "max_transactions": max_transactions, "status": "timeout", "error": f"Timeout after {timeout_sec} seconds."}


def make_result_fieldnames() -> List[str]:
    return ["experiment", "algorithm", "dataset", "file", "algorithm_file", "threshold_index", "size_fraction", "max_transactions", "min_utility", "central_percentage", "threshold_mode", "runtime_ms", "baseline_memory_mb", "peak_memory_mb", "delta_memory_mb", "algorithm_internal_memory_mb", "pattern_count", "output_pattern_lines", "candidate_count", "case1_count", "case2_count", "read_transactions", "read_total_utility", "read_entries", "read_unique_items", "status", "error", "stderr_tail"]


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
        for row in csv.DictReader(f):
            keys.add(tuple(row.get(field, "") for field in key_fields))
    return keys


def write_dataset_summary(summary_path: Path, rows: List[Dict[str, object]]) -> None:
    fieldnames = ["dataset", "file", "transaction_count", "total_utility", "entry_count", "unique_item_count", "central_percentage", "central_min_utility"]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_master(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    algo_dir = Path(args.algo_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    script_path = Path(__file__).resolve()
    selected_datasets = args.datasets or list(DATASET_FILES.keys())
    selected_algorithms = args.algorithms or DEFAULT_ALGORITHMS

    for name in selected_datasets:
        if name not in DATASET_FILES:
            raise ValueError(f"Unknown dataset name: {name}")
    for name in selected_algorithms:
        if name not in ALGORITHM_FILES:
            raise ValueError(f"Unknown algorithm name: {name}")

    result_fields = make_result_fieldnames()
    threshold_csv = out_dir / "baseline_huim_threshold_results.csv"
    scalability_csv = out_dir / "baseline_huim_scalability_results.csv"
    summary_csv = out_dir / "baseline_huim_dataset_summary.csv"

    threshold_keys = load_completed_keys(threshold_csv, ["experiment", "algorithm", "dataset", "threshold_index", "min_utility", "max_transactions"])
    scalability_keys = load_completed_keys(scalability_csv, ["experiment", "algorithm", "dataset", "size_fraction", "min_utility", "max_transactions"])

    # Preserve the most recent status for each threshold result.
    # This allows the early-stop rule to survive process restarts.
    threshold_statuses = {}
    if threshold_csv.exists():
        with threshold_csv.open("r", encoding="utf-8", newline="") as f:
            for existing_row in csv.DictReader(f):
                status_key = (
                    existing_row.get("experiment", ""),
                    existing_row.get("algorithm", ""),
                    existing_row.get("dataset", ""),
                    existing_row.get("threshold_index", ""),
                    existing_row.get("min_utility", ""),
                    existing_row.get("max_transactions", ""),
                )
                threshold_statuses[status_key] = existing_row.get("status", "")

    print(f"Data directory:      {data_dir}")
    print(f"Algorithm directory: {algo_dir}")
    print(f"Output directory:    {out_dir}")
    print(f"Datasets:            {', '.join(selected_datasets)}")
    print(f"Algorithms:          {', '.join(selected_algorithms)}\n")

    dataset_info: Dict[str, Dict[str, object]] = {}
    summary_rows = []
    for dataset in selected_datasets:
        file_path = find_dataset_file(data_dir, dataset)
        print(f"Scanning {dataset}: {file_path.name}")
        stats = scan_dataset_stats(file_path)
        dataset_info[dataset] = {"dataset": dataset, "file_path": file_path, **stats, "central_percentage": CENTRAL_PERCENTAGES[dataset], "central_min_utility": MIN_UTIL_THRESHOLDS[dataset][3]}
        summary_rows.append({"dataset": dataset, "file": file_path.name, **stats, "central_percentage": CENTRAL_PERCENTAGES[dataset], "central_min_utility": MIN_UTIL_THRESHOLDS[dataset][3]})
    write_dataset_summary(summary_csv, summary_rows)

    algorithm_paths: Dict[str, Path] = {}
    for algorithm in selected_algorithms:
        try:
            algorithm_paths[algorithm] = find_algorithm_file(algo_dir, algorithm)
        except FileNotFoundError as exc:
            print(f"[missing] {exc}")
            if not args.skip_missing_algorithms:
                raise

    if args.run_thresholds:
        for algorithm, algorithm_file in algorithm_paths.items():
            for dataset in selected_datasets:
                thresholds = list(enumerate(MIN_UTIL_THRESHOLDS[dataset], start=1))
                if args.high_to_low:
                    thresholds = thresholds[::-1]
                else:
                    print(
                        f"[warn] {algorithm} {dataset}: timeout early-stop is "
                        "disabled because thresholds are not running high-to-low."
                    )

                blocked_after_timeout = False

                for threshold_index, min_utility in thresholds:
                    key = (
                        "threshold",
                        algorithm,
                        dataset,
                        str(threshold_index),
                        str(min_utility),
                        "",
                    )

                    existing_status = (
                        threshold_statuses.get(key, "")
                        if not args.overwrite
                        else ""
                    )

                    # Existing results are normally skipped.  Importantly,
                    # an existing timeout also activates the stopping rule
                    # after a restart.
                    if existing_status:
                        print(
                            f"[skip] threshold {algorithm} {dataset} "
                            f"T{threshold_index} minUtil={min_utility} "
                            f"status={existing_status}"
                        )

                        if (
                            args.high_to_low
                            and existing_status
                            in {"timeout", "skipped_after_timeout"}
                        ):
                            blocked_after_timeout = True

                        continue

                    # Once a higher threshold timed out, do not execute any
                    # lower min-utility thresholds for this algorithm/dataset.
                    if args.high_to_low and blocked_after_timeout:
                        skip_result = {
                            "algorithm": algorithm,
                            "dataset": dataset,
                            "file": str(dataset_info[dataset]["file_path"]),
                            "algorithm_file": str(algorithm_file),
                            "min_utility": min_utility,
                            "max_transactions": None,
                            "status": "skipped_after_timeout",
                            "error": (
                                "Not executed because a higher min-utility "
                                "threshold for this algorithm/dataset reached "
                                f"the {args.timeout_sec}-second timeout."
                            ),
                        }

                        row = {
                            "experiment": "threshold",
                            "threshold_index": threshold_index,
                            "size_fraction": "",
                            "central_percentage": CENTRAL_PERCENTAGES[dataset],
                            "threshold_mode": "absolute",
                            **skip_result,
                        }

                        append_csv_row(threshold_csv, row, result_fields)
                        threshold_keys.add(key)
                        threshold_statuses[key] = "skipped_after_timeout"

                        print(
                            f"[skip-timeout] threshold {algorithm} {dataset} "
                            f"T{threshold_index} minUtil={min_utility}"
                        )
                        continue

                    print(
                        f"[run ] threshold {algorithm} {dataset} "
                        f"T{threshold_index} minUtil={min_utility}"
                    )

                    result = run_one_subprocess(
                        script_path,
                        algorithm,
                        algorithm_file,
                        dataset,
                        dataset_info[dataset]["file_path"],
                        min_utility,
                        None,
                        args.timeout_sec,
                        args.sample_interval,
                        args.include_unsafe,
                        args.max_unique_items_unsafe,
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

                    threshold_keys.add(key)
                    threshold_statuses[key] = str(row["status"])

                    print(
                        f"       status={row['status']} "
                        f"runtime={row.get('runtime_ms', '')} ms "
                        f"peak={row.get('peak_memory_mb', '')} MB "
                        f"patterns={row.get('pattern_count', '')}"
                    )

                    if args.high_to_low and row["status"] == "timeout":
                        blocked_after_timeout = True
                        print(
                            f"[early-stop] {algorithm} {dataset}: "
                            f"T{threshold_index} reached timeout; "
                            "all lower thresholds will be skipped."
                        )

    if args.run_scalability:
        # ------------------------------------------------------------
        # BDA8 scalability protocol
        #
        # All algorithms MUST use:
        #   fractions: 20%, 40%, 60%, 80%, 100%
        #   fixed absolute minUtility for each dataset
        #   identical first-N transaction prefixes
        #   identical timeout policy
        # ------------------------------------------------------------
        expected_scalability_fractions = [0.20, 0.40, 0.60, 0.80, 1.00]

        actual_fractions = [
            round(float(x), 2)
            for x in args.scalability_fractions
        ]

        if actual_fractions != expected_scalability_fractions:
            raise ValueError(
                "BDA8 scalability requires fractions exactly "
                "0.20 0.40 0.60 0.80 1.00 in ascending order. "
                f"Received: {actual_fractions}"
            )

        if args.scalability_threshold_mode != "absolute":
            raise ValueError(
                "BDA8 scalability requires "
                "--scalability-threshold-mode absolute "
                "so every algorithm uses the same fixed minUtility "
                "as PA-HUIM."
            )

        # Preserve the latest status of each scalability experiment.
        # This allows timeout early-stop to survive process restarts.
        scalability_statuses = {}

        if scalability_csv.exists():
            with scalability_csv.open(
                "r",
                encoding="utf-8",
                newline=""
            ) as f:
                for existing_row in csv.DictReader(f):
                    raw_fraction = existing_row.get(
                        "size_fraction", ""
                    )

                    try:
                        fraction_key = (
                            f"{float(raw_fraction):.2f}"
                        )
                    except Exception:
                        fraction_key = raw_fraction

                    status_key = (
                        existing_row.get("experiment", ""),
                        existing_row.get("algorithm", ""),
                        existing_row.get("dataset", ""),
                        fraction_key,
                        existing_row.get("min_utility", ""),
                        existing_row.get("max_transactions", ""),
                    )

                    scalability_statuses[status_key] = (
                        existing_row.get("status", "")
                    )

        for algorithm, algorithm_file in algorithm_paths.items():
            for dataset in selected_datasets:

                total_transactions = int(
                    dataset_info[dataset]["transaction_count"]
                )

                # Fixed absolute minUtility used by PA-HUIM.
                min_utility = MIN_UTIL_THRESHOLDS[dataset][3]

                blocked_after_timeout = False

                for fraction in expected_scalability_fractions:

                    max_transactions = max(
                        1,
                        int(round(
                            total_transactions * fraction
                        ))
                    )

                    key = (
                        "scalability",
                        algorithm,
                        dataset,
                        f"{fraction:.2f}",
                        str(min_utility),
                        str(max_transactions),
                    )

                    existing_status = (
                        scalability_statuses.get(key, "")
                        if not args.overwrite
                        else ""
                    )

                    # Existing successful/terminal results are retained.
                    # Existing timeout/skipped rows also reactivate the
                    # early-stop boundary after a restart.
                    if existing_status in {
                        "ok",
                        "timeout",
                        "skipped_after_timeout",
                    }:
                        print(
                            f"[skip] scalability {algorithm} "
                            f"{dataset} fraction={fraction:.2f} "
                            f"minUtil={min_utility} "
                            f"status={existing_status}"
                        )

                        if existing_status in {
                            "timeout",
                            "skipped_after_timeout",
                        }:
                            blocked_after_timeout = True

                        continue

                    # Previous errors are rerun rather than treated as
                    # completed experiments.
                    if existing_status:
                        print(
                            f"[rerun] scalability {algorithm} "
                            f"{dataset} fraction={fraction:.2f} "
                            f"previous_status={existing_status}"
                        )

                    # Once a smaller fraction reaches the timeout,
                    # larger fractions are intentionally not executed.
                    if blocked_after_timeout:
                        skip_result = {
                            "algorithm": algorithm,
                            "dataset": dataset,
                            "file": str(
                                dataset_info[dataset]["file_path"]
                            ),
                            "algorithm_file": str(algorithm_file),
                            "min_utility": min_utility,
                            "max_transactions": max_transactions,
                            "status": "skipped_after_timeout",
                            "error": (
                                "Not executed because a smaller "
                                "dataset fraction for this "
                                "algorithm/dataset reached the "
                                f"{args.timeout_sec}-second timeout."
                            ),
                        }

                        row = {
                            "experiment": "scalability",
                            "threshold_index": "",
                            "size_fraction": f"{fraction:.2f}",
                            "central_percentage":
                                CENTRAL_PERCENTAGES[dataset],
                            "threshold_mode": "absolute",
                            **skip_result,
                        }

                        append_csv_row(
                            scalability_csv,
                            row,
                            result_fields
                        )

                        scalability_keys.add(key)
                        scalability_statuses[key] = (
                            "skipped_after_timeout"
                        )

                        print(
                            f"[skip-timeout] scalability "
                            f"{algorithm} {dataset} "
                            f"fraction={fraction:.2f} "
                            f"maxTrans={max_transactions}"
                        )

                        continue

                    print(
                        f"[run ] scalability {algorithm} "
                        f"{dataset} "
                        f"fraction={fraction:.2f} "
                        f"maxTrans={max_transactions} "
                        f"minUtil={min_utility}"
                    )

                    result = run_one_subprocess(
                        script_path,
                        algorithm,
                        algorithm_file,
                        dataset,
                        dataset_info[dataset]["file_path"],
                        min_utility,
                        max_transactions,
                        args.timeout_sec,
                        args.sample_interval,
                        args.include_unsafe,
                        args.max_unique_items_unsafe,
                    )

                    row = {
                        "experiment": "scalability",
                        "threshold_index": "",
                        "size_fraction": f"{fraction:.2f}",
                        "central_percentage":
                            CENTRAL_PERCENTAGES[dataset],
                        "threshold_mode": "absolute",
                        **result,
                    }

                    append_csv_row(
                        scalability_csv,
                        row,
                        result_fields
                    )

                    scalability_keys.add(key)
                    scalability_statuses[key] = str(
                        row["status"]
                    )

                    print(
                        f"       status={row['status']} "
                        f"runtime={row.get('runtime_ms', '')} ms "
                        f"peak={row.get('peak_memory_mb', '')} MB "
                        f"patterns={row.get('pattern_count', '')}"
                    )

                    if row["status"] == "timeout":
                        blocked_after_timeout = True

                        print(
                            f"[early-stop] scalability "
                            f"{algorithm} {dataset}: "
                            f"fraction={fraction:.2f} reached "
                            "timeout; all larger fractions "
                            "will be skipped."
                        )

    print("\nFinished.")
    print(f"Threshold results:   {threshold_csv}")
    print(f"Scalability results: {scalability_csv}")
    print(f"Dataset summary:     {summary_csv}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=".")
    parser.add_argument("--algo-dir", default=".")
    parser.add_argument("--out-dir", default="baseline_huim_results")
    parser.add_argument("--datasets", nargs="*", default=None)
    parser.add_argument("--algorithms", nargs="*", default=None, help="efim fhm upgrowthplus d2hup hui_miner ulb_miner")
    parser.add_argument("--run-thresholds", action="store_true")
    parser.add_argument("--run-scalability", action="store_true")
    parser.add_argument("--high-to-low", action="store_true", default=True)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--timeout-sec", type=int, default=None)
    parser.add_argument("--sample-interval", type=float, default=0.05)
    parser.add_argument("--skip-missing-algorithms", action="store_true")
    parser.add_argument("--include-unsafe", action="store_true")
    parser.add_argument("--max-unique-items-unsafe", type=int, default=22)
    parser.add_argument("--scalability-fractions", type=float, nargs="*", default=SCALABILITY_FRACTIONS)
    parser.add_argument("--scalability-threshold-mode", choices=["percentage", "absolute"], default="absolute")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--algorithm", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--algorithm-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--dataset", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--file", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--min-utility", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--max-transactions", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.run_thresholds and not args.run_scalability and not args.worker:
        args.run_thresholds = True
        args.run_scalability = True
    if args.worker:
        required = [args.algorithm, args.algorithm_file, args.dataset, args.file, args.min_utility]
        if any(x is None for x in required):
            parser.error("--worker requires --algorithm, --algorithm-file, --dataset, --file, and --min-utility")
    return args


if __name__ == "__main__":
    parsed_args = parse_args()
    if parsed_args.worker:
        run_worker(parsed_args)
    else:
        run_master(parsed_args)
