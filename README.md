# PA-HUIM

**PA-HUIM: A Pure-Array Projected Algorithm for Efficient High-Utility Itemset Mining**

This repository contains the implementation, benchmark datasets, baseline implementations, raw experimental outputs, and result-consolidation scripts used for the PA-HUIM study.

Repository: https://github.com/taiduydinh/pa-huim

## Overview

PA-HUIM is an exact high-utility itemset mining (HUIM) algorithm based on a pure-array projected representation. After transaction-weighted-utilization (TWU) filtering, the filtered database is stored once in flat arrays for transaction boundaries, ordered item identifiers, occurrence utilities, and suffix utilities. Recursive search states use compact projection arrays for transaction identifiers, matched positions, and prefix utilities. Reusable item-indexed arrays accumulate exact extension utilities and descendant upper bounds.

The experimental evaluation compares PA-HUIM with six exact HUIM baselines:

- EFIM
- FHM
- HUI-Miner
- ULB-Miner
- UP-Growth+
- d2HUP

The final benchmark contains eight datasets, ten minimum-utility thresholds per dataset, and five database fractions for scalability.

## Final experimental matrix

The final protocol contains:

- 7 algorithms
- 8 datasets
- 10 threshold settings per dataset
- 5 scalability settings per dataset

This gives **840 experiment cells** in total.

The final consolidated status is:

| Status | Cells |
|---|---:|
| Correct / count-verified | 798 |
| 36-hour timeout | 8 |
| Protocol-skipped after predecessor timeout | 29 |
| Explicitly excluded | 5 |
| Pending | 0 |
| **Total** | **840** |

Every successful baseline result was cross-checked against the PA-HUIM HUI count for the same task. No successful result in the final consolidated matrix has a count mismatch.

## Repository structure

Important top-level files and directories are:

```text
pa-huim/
├── run_pa_huim.py                  # PA-HUIM experiment runner
├── run_baseline_huim.py            # Common runner for the six baselines
├── efim.py
├── fhm.py
├── hui_miner.py
├── ulb_miner.py
├── up_growthplus.py
├── d2hup.py                        # Corrected version used in final experiments
│
├── datasets/                       # Eight final benchmark datasets
├── data/                           # Final consolidated result files
│   ├── canonical_final.csv
│   ├── dataset_stats.csv
│   └── status_summary.csv
│
├── pa_huim_results/                # Raw PA-HUIM threshold/scalability results
├── baseline_huim_results/          # Main baseline results
├── baseline_scalability/           # Baseline scalability results
├── baseline_*/                     # Recovery and algorithm-specific raw results
├── first8_batch/
├── next*_batch/
├── final3_batch/
├── speculative_accel/
├── reuse_t4_100_archive/
├── excluded_up_ecommerce_scalability/
├── memory_pressure_archive/
│
├── provenance/                     # Records of implementation fixes
├── reuse_t4_100_manifest.tsv       # T4 / 100% reuse record
├── build_final_results.py          # Rebuild the final 840-cell matrix
├── audit_all.py
├── audit_scalability.py
├── DATASETS.md
└── requirements.txt
```

The raw result directories are intentionally retained because `build_final_results.py` discovers and consolidates the relevant CSV and JSON outputs recursively. If you want to reproduce the published consolidation, do not rename or remove those directories before running the rebuild script.

## Software environment

The experiments were executed using:

- Python 3.11.5
- Conda 23.7.4
- Docker 20.10.21
- Ubuntu 20.04.6 LTS
- Linux kernel 5.4.0-131-generic

The benchmark server used:

- 2 × Intel Xeon Gold 6252 @ 2.10 GHz
- 48 physical cores / 96 logical CPUs
- 1.0 TiB RAM

Independent experiment cases were pinned to distinct physical cores, avoiding hyper-thread siblings where possible. Peak resident set size (RSS) was sampled every 0.05 s.

## Installation

Python 3.11 is recommended.

Using Conda:

```bash
conda create -n pa-huim python=3.11.5 -y
conda activate pa-huim
pip install -r requirements.txt
```

The large benchmark files `chainstore.txt`, `accidents.txt`, and `kosarak.txt` are tracked with Git LFS. After cloning, make sure Git LFS is installed and fetch the LFS objects:

```bash
git lfs install
git lfs pull
```

## Verify the archived results

The simplest reproducibility check is to reconstruct the complete final matrix from the raw result artifacts:

```bash
python build_final_results.py . --out data_rebuilt
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

The `Pending:` section should be empty.

The generated files in `data_rebuilt/` can then be compared with the released files under `data/`.

## Run PA-HUIM

The runner supports threshold and scalability experiments. To run the final eight-dataset protocol:

```bash
python run_pa_huim.py \
  --data-dir datasets \
  --out-dir pa_huim_results_reproduced \
  --datasets foodmart ecommerce retail fruithut accidents kosarak chainstore chicago_crimes \
  --run-thresholds \
  --run-scalability \
  --high-to-low \
  --timeout-sec 129600 \
  --sample-interval 0.05 \
  --scalability-threshold-mode absolute
```

On Windows CMD, place the command on one line or use `^` for line continuation.

Use `python run_pa_huim.py --help` for all options.

The benchmark runner counts discovered HUIs by default rather than storing every pattern in memory. The `--store-patterns` option is intended for smaller tests and is not recommended for the large benchmark configurations.

## Run the baselines

To run the six baseline algorithms under the same high-level protocol:

```bash
python run_baseline_huim.py \
  --data-dir datasets \
  --algo-dir . \
  --out-dir baseline_results_reproduced \
  --datasets foodmart ecommerce retail fruithut accidents kosarak chainstore chicago_crimes \
  --algorithms efim fhm hui_miner ulb_miner upgrowthplus d2hup \
  --run-thresholds \
  --run-scalability \
  --high-to-low \
  --timeout-sec 129600 \
  --sample-interval 0.05 \
  --scalability-threshold-mode absolute
```

Use `python run_baseline_huim.py --help` for all options.

Some configurations require many hours or substantial memory. Re-running the full experiment matrix is therefore not necessary merely to verify the reported results; the released raw outputs and `build_final_results.py` provide a deterministic reconstruction of the final matrix.

## Experimental protocol

### Threshold experiment

Each dataset is evaluated at ten absolute minimum-utility settings, T10 (highest/easiest) through T1 (lowest/hardest).

The threshold progression is interpreted sequentially from T10 to T1. If an algorithm reaches the 36-hour timeout at setting Ti, Ti is reported as timeout and all lower-threshold settings are reported as protocol-skipped, even if a harder case was launched speculatively.

### Scalability experiment

Scalability uses the first 20%, 40%, 60%, 80%, and 100% of the valid transaction sequence.

The minimum utility is fixed at the dataset's T4 threshold. Therefore, the 100% scalability task is identical to the full-dataset T4 threshold task. The same canonical execution is reused for both analyses rather than treating duplicate executions as independent measurements.

The scalability predecessor rule is analogous to the threshold rule: once a smaller fraction times out, larger fractions are not admitted into the final analysis.

### Explicit exclusion

The five UP-Growth+ Ecommerce scalability cells are marked `excluded`, not `timeout` or `incorrect`. Trial executions caused severe memory pressure in the experimental environment. The exclusion record is preserved under `excluded_up_ecommerce_scalability/`.

## Correctness and provenance

The repository preserves the implementation and result provenance used in the final study.

In particular:

- `d2hup.py` is the corrected d2HUP implementation used for the final experiments.
- Details related to the d2HUP transaction-order correction and the UP-Growth+ fix are preserved under `provenance/`.
- `reuse_t4_100_manifest.tsv` records the reuse relationship between full-data T4 and the 100% scalability setting.
- Raw recovery/speculative executions are retained for auditability, while the final matrix applies the predecessor rules consistently.

## Final result files

`data/canonical_final.csv` is the primary machine-readable final matrix.

`data/status_summary.csv` summarizes the final status counts.

`data/dataset_stats.csv` contains the dataset statistics used in the manuscript.

The final paper-level findings include:

- PA-HUIM has the lowest peak RSS among completed alternatives at 70 of 80 threshold settings.
- PA-HUIM is the fastest method among completed alternatives at 22 threshold settings.
- The strongest runtime advantages occur on Ecommerce and Kosarak.
- Other methods remain faster on several datasets, and UP-Growth+ is substantially more memory-efficient on Chicago Crimes.

The repository therefore supports both the positive findings and the reported limitations of the proposed design.

## Datasets

See [DATASETS.md](DATASETS.md) for statistics, file checksums, input format, Git LFS information, and redistribution notes.

## Citation

If you use this code or experimental package, please cite the accompanying manuscript:

**Tai Dinh. “PA-HUIM: A Pure-Array Projected Algorithm for Efficient High-Utility Itemset Mining.”**

Full proceedings metadata can be added here when the final bibliographic record becomes available.

## Reproducibility contact

Tai Dinh  
The Kyoto College of Graduate Studies for Informatics, Japan  
https://github.com/taiduydinh/pa-huim
