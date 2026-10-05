PA-HUIM BDA 2026 - completed-results update
===========================================

Primary manuscript:
  PA_HUIM_BDA2026_full_updated.tex
  PA_HUIM_BDA2026_full_updated.pdf

Result source used for this update:
  MP6_Kazi_full_20261005_121308.zip

Final protocol-aware status of the 840 experiment cells:
  Correct / count-verified : 798
  Reported 36-hour timeout : 8
  Skipped after timeout    : 29
  Explicitly excluded      : 5
  Pending                  : 0
  Total                    : 840

Per-algorithm status:
  PA-HUIM      120 correct
  EFIM         120 correct
  FHM          108 correct, 2 timeout, 10 skipped
  HUI-Miner    117 correct, 1 timeout, 2 skipped
  ULB-Miner    120 correct
  UP-Growth+    93 correct, 5 timeout, 17 skipped, 5 excluded
  d2HUP        120 correct

Important protocol interpretation:
- Thresholds are interpreted T10 -> T1. Once a setting times out, all lower
  thresholds are reported as skipped, even if speculative raw processes later
  timed out or were manually terminated.
- Scalability is interpreted 20% -> 100% in the same way.
- The 100% scalability task is identical to the full-data T4 task and reuses
  that execution where admissible.
- UP-Growth+ Ecommerce scalability (20/40/60/80/100%) is explicitly excluded
  because trial executions caused severe memory pressure; these cells are not
  counted as timeout or correctness failures.

Reported timeout cells after applying the predecessor protocol:
  Threshold:
    FHM          Accidents   T10
    HUI-Miner    Ecommerce   T3
    UP-Growth+   Accidents   T10
    UP-Growth+   Chainstore  T1
    UP-Growth+   Ecommerce   T9
    UP-Growth+   Fruithut    T1
  Scalability:
    FHM          Accidents   80%
    UP-Growth+   Accidents   100% (same task as full-data T4)

New completed results incorporated relative to the previous manuscript snapshot:
- HUI-Miner Chainstore T1: 109,200.242 s (30.33 h), 933.582 MB,
  43,785,109 HUIs; count matches PA-HUIM.
- UP-Growth+ Accidents scalability 80%: 85,319.837 s (23.70 h),
  600.414 MB, 7 HUIs; count matches PA-HUIM.
- All former pending threshold/scalability cells are now resolved through
  success, timeout, predecessor skip, or the documented exclusion.

Files:
  data/canonical_final.csv   protocol-aware 840-cell consolidated matrix
  data/status_summary.csv   per-algorithm status counts
  data/dataset_stats.csv    dataset statistics used in the manuscript
  figures/*.pdf             regenerated vector plots from canonical_final.csv
  build_final_results.py    consolidation script; run against an extracted
                            MP6_Kazi folder, e.g.:
      python build_final_results.py /path/to/MP6_Kazi --out data_rebuilt

The PDF compiles to 15 pages, matching the BDA 2026 maximum used for this draft.
The experimental environment is now fully specified in the TeX: dual Intel Xeon Gold 6252 CPUs (48 physical/96 logical CPUs), 1.0 TiB RAM, Ubuntu 20.04.6 LTS, Docker 20.10.21, Python 3.11.5, and Conda 23.7.4.
because those host-environment details were not stored in the uploaded project
folder and were not inferred.

The experimental environment is now fully specified in the TeX: dual Intel Xeon Gold 6252 CPUs (2.10 GHz; 48 physical/96 logical CPUs), 1.0 TiB RAM, Ubuntu 20.04.6 LTS (kernel 5.4.0-131-generic), Docker 20.10.21, Python 3.11.5, and Conda 23.7.4.
