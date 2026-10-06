# PA-HUIM

**PA-HUIM: A Pure-Array Projected Algorithm for Efficient High-Utility Itemset Mining**

This repository provides the implementation, benchmark datasets, and experimental results used in the PA-HUIM study.

Repository: https://github.com/taiduydinh/pa-huim

## Overview

PA-HUIM is an exact high-utility itemset mining (HUIM) algorithm based on a pure-array projected representation. After transaction-weighted-utilization (TWU) filtering, the filtered database is stored once in flat arrays for transaction boundaries, ordered item identifiers, occurrence utilities, and suffix utilities. Recursive search states use compact projection arrays for transaction identifiers, matched positions, and prefix utilities. Reusable item-indexed arrays accumulate exact extension utilities and descendant upper bounds.

The evaluation compares PA-HUIM with six exact HUIM baselines:

- EFIM
- FHM
- HUI-Miner
- ULB-Miner
- UP-Growth+
- d2HUP

The final benchmark uses eight datasets, ten minimum-utility thresholds per dataset, and five database fractions for scalability.

## Repository structure

The public repository is organized into three main folders:

```text
pa-huim/
├── datasets/                         # Eight benchmark datasets
├── codes/                            # Algorithms and experiment utilities
├── experimental_results/             # Final results and archived raw runs
├── README.md
├── DATASETS.md
└── requirements.txt
```

### `codes/`

```text
codes/
├── run_pa_huim.py
├── run_baseline_huim.py
├── efim.py
├── fhm.py
├── hui_miner.py
├── ulb_miner.py
├── up_growthplus.py
├── d2hup.py
├── build_final_results.py
├── audit_all.py
└── audit_scalability.py
```

### `experimental_results/`

```text
experimental_results/
├── canonical_final.csv
├── dataset_stats.csv
├── status_summary.csv
├── reuse_t4_100_manifest.tsv
├── upgrowthplus_ecommerce_exclusion.txt
├── raw_runs/
└── provenance/
```

For normal result checking, readers only need the files directly under `experimental_results/`. The `raw_runs/` directory preserves the original execution batches used to construct the final matrix. Internal folder names such as `parallel`, `tail`, `next`, or `final` are execution bookkeeping labels and are not separate algorithms or experimental protocols.

`canonical_final.csv` is the primary machine-readable result file and contains the complete protocol-aware experimental matrix.

## Final experimental matrix

The final protocol contains **840 experiment cells**:

| Status | Cells |
|---|---:|
| Correct / count-verified | 798 |
| 36-hour timeout | 8 |
| Protocol-skipped after predecessor timeout | 29 |
| Explicitly excluded | 5 |
| Pending | 0 |
| **Total** | **840** |

Every completed baseline result was cross-checked against the PA-HUIM HUI count for the same mining task. No completed exact comparison in the final matrix has a count mismatch.

## Software environment

The experiments were executed using:

- Python 3.11.5
- Conda 23.7.4
- Docker 20.10.21
- Ubuntu 20.04.6 LTS
- Linux kernel 5.4.0-131-generic

Benchmark server:

- 2 × Intel Xeon Gold 6252 @ 2.10 GHz
- 48 physical cores / 96 logical CPUs
- 1.0 TiB RAM

Independent cases were pinned to distinct physical cores, avoiding hyper-thread siblings where possible. Peak resident set size (RSS) was sampled every 0.05 s.

## Installation

Python 3.11 is recommended.

```bash
conda create -n pa-huim python=3.11.5 -y
conda activate pa-huim
pip install -r requirements.txt
```

The large datasets `chainstore.txt`, `accidents.txt`, and `kosarak.txt` are tracked with Git LFS:

```bash
git lfs install
git lfs pull
```

## Verify the archived results

The final 840-cell matrix can be reconstructed from the archived raw runs:

```bash
python codes/build_final_results.py experimental_results/raw_runs --out experimental_results/rebuilt
```

Expected summary:

```text
Per algorithm:
pa_huim {'correct': 120}
efim {'correct': 120}
fhm {'correct': 108, 'timeout': 2, 'skipped': 10}
hui_miner {'correct': 117, 'timeout': 1, 'skipped': 2}
ulb_miner {'correct': 120}
upgrowthplus {'correct': 93, 'timeout': 5, 'skipped': 17, 'excluded': 5}
d2hup {'correct': 120}

TOTAL {'correct': 798, 'timeout': 8, 'skipped': 29, 'excluded': 5} sum 840
```

The `Pending:` section should be empty. The regenerated files under `experimental_results/rebuilt/` can then be compared with the released files directly under `experimental_results/`.

## Run PA-HUIM

```bash
python codes/run_pa_huim.py \
  --data-dir datasets \
  --out-dir experimental_results/reproduced_pa_huim \
  --datasets foodmart ecommerce retail fruithut accidents kosarak chainstore chicago_crimes \
  --run-thresholds \
  --run-scalability \
  --high-to-low \
  --timeout-sec 129600 \
  --sample-interval 0.05 \
  --scalability-threshold-mode absolute
```

Use `python codes/run_pa_huim.py --help` for all options.

## Run the baselines

```bash
python codes/run_baseline_huim.py \
  --data-dir datasets \
  --algo-dir codes \
  --out-dir experimental_results/reproduced_baselines \
  --datasets foodmart ecommerce retail fruithut accidents kosarak chainstore chicago_crimes \
  --algorithms efim fhm hui_miner ulb_miner upgrowthplus d2hup \
  --run-thresholds \
  --run-scalability \
  --high-to-low \
  --timeout-sec 129600 \
  --sample-interval 0.05 \
  --scalability-threshold-mode absolute
```

Some configurations require many hours and substantial memory. The published results are therefore provided directly in `experimental_results/canonical_final.csv`.

## Experimental protocol

### Threshold experiment

Each dataset is evaluated at ten absolute minimum-utility settings, T10 (highest/easiest) through T1 (lowest/hardest).

If an algorithm reaches the 36-hour timeout at setting Ti, Ti is reported as timeout and all lower thresholds are reported as protocol-skipped.

### Scalability experiment

Scalability uses the first 20%, 40%, 60%, 80%, and 100% of the valid transaction sequence.

The minimum utility is fixed at the dataset's T4 threshold. The 100% scalability task is therefore identical to the full-dataset T4 task, and the final analysis reuses the same canonical execution.

### UP-Growth+ Ecommerce exclusion

The five UP-Growth+ Ecommerce scalability cells are marked `excluded`, not `timeout` or `incorrect`, because trial executions caused severe memory pressure. Details are provided in `experimental_results/upgrowthplus_ecommerce_exclusion.txt`.

## Final result files

- `experimental_results/canonical_final.csv`: complete 840-cell final result matrix.
- `experimental_results/status_summary.csv`: per-algorithm status counts.
- `experimental_results/dataset_stats.csv`: dataset statistics used in the paper.
- `experimental_results/reuse_t4_100_manifest.tsv`: records T4 / 100% task reuse.
- `experimental_results/upgrowthplus_ecommerce_exclusion.txt`: documents the explicit UP-Growth+ Ecommerce scalability exclusion.

The main findings include:

- PA-HUIM has the lowest peak RSS among completed alternatives at 70 of 80 threshold settings.
- PA-HUIM is the fastest method among completed alternatives at 22 threshold settings.
- The strongest runtime advantages occur on Ecommerce and Kosarak.
- Other methods remain faster on several datasets, and UP-Growth+ is substantially more memory-efficient on Chicago Crimes.

## Datasets

See [DATASETS.md](DATASETS.md) for dataset statistics, checksums, input format, Git LFS information, and redistribution notes.

## Citation

If you use this code or experimental package, please cite the accompanying paper. The manuscript has been submitted to the **14th International Conference on Big Data Analytics in Astronomy, Science and Engineering (BDA 2026)**.

```bibtex
@unpublished{dinh2026pahuim,
  author = {Tai Dinh},
  title = {PA-HUIM: A Pure-Array Projected Algorithm for Efficient High-Utility Itemset Mining},
  note = {Submitted to the 14th International Conference on Big Data Analytics in Astronomy, Science and Engineering (BDA 2026)},
  year = {2026}
}
```
