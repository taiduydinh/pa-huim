# Datasets

This directory contains the eight utility-transaction datasets used in the final PA-HUIM benchmark.

## Final benchmark datasets

| Dataset | File | Valid transactions | Unique items | Item occurrences | Avg. length | Total utility | Approx. file size |
|---|---|---:|---:|---:|---:|---:|---:|
| Foodmart | `foodmart.txt` | 4,141 | 1,559 | 18,319 | 4.42 | 12,011,023 | 0.17 MiB |
| Ecommerce | `ecommerce.txt` | 14,975 | 3,468 | 174,354 | 11.64 | 497,013,754 | 1.92 MiB |
| Retail | `retail.txt` | 88,162 | 16,470 | 908,576 | 10.31 | 14,910,915 | 6.51 MiB |
| Fruithut | `fruithut.txt` | 181,970 | 1,265 | 652,773 | 3.59 | 261,871,526 | 6.63 MiB |
| Accidents | `accidents.txt` | 340,183 | 468 | 11,500,870 | 33.81 | 196,141,636 | 63.17 MiB |
| Kosarak | `kosarak.txt` | 990,002 | 41,270 | 8,019,015 | 8.10 | 140,925,416 | 53.34 MiB |
| Chainstore | `chainstore.txt` | 1,112,949 | 46,086 | 8,042,879 | 7.23 | 2,609,973,588 | 79.20 MiB |
| Chicago Crimes | `chicago_crimes.txt` | 2,662,309 | 35 | 4,781,456 | 1.80 | 7,941,285 | 27.80 MiB |

The statistics above are the values used in the final manuscript and are also stored in `data/dataset_stats.csv`.

## Input format

The benchmark uses an SPMF-style utility-transaction format. A normal transaction line has the form:

```text
item1 item2 ... itemN : transactionUtility : utility1 utility2 ... utilityN
```

For example:

```text
1 2 3:32:9 18 5
```

means that the transaction contains items `1`, `2`, and `3`, has transaction utility `32`, and the corresponding occurrence utilities are `9`, `18`, and `5`.

Blank lines and metadata/comment lines beginning with `#`, `%`, or `@` are ignored by the PA-HUIM parser.

## Fruithut validity rule

`fruithut.txt` contains 183,236 raw physical lines. Under the common parser used for the final benchmark, 181,970 lines are valid SPMF utility transactions and 1,266 non-transaction/malformed structural lines are excluded.

All scalability fractions for Fruithut are formed from the valid transaction sequence, not from the raw physical line count.

## Dataset integrity

SHA-256 checksums for the exact dataset files used in the final experiments are:

```text
foodmart.txt
0e77ec1b913f6ace0905dac16811bfe2c78e13c32d07647d316e593042d970e6

ecommerce.txt
460ddc4fd3816a5c7ddc2f95b00164976f3f5c8e39585a994f56596ebcaa355c

retail.txt
36b9bf346bd90c7588553dadbc1e549096f9246e864c3418861b1d2f7bd4f019

fruithut.txt
8f361167e74de7fc3e7668474095435c51a0ce9cea116734499dcf680a0a9890

accidents.txt
6ff606761f8716789ae67bd2e871fdd319ea248e60c265cccaba5a3b8897b9a0

kosarak.txt
b137b0f44ed3cd9dbb9c804bfc4b724aaad25d9b5b0d0e229009cf5d8a99831f

chainstore.txt
50e5a843df38b187ad99c1ae0c291d8626fb50f98cf5cea3468e312294a79dbb

chicago_crimes.txt
98bdd91dff4daa6788196f81566a680ddd64c86c071198251aea96277b679279
```

On Linux/macOS:

```bash
sha256sum datasets/*.txt
```

On Windows PowerShell:

```powershell
Get-FileHash datasets\*.txt -Algorithm SHA256
```

## Git LFS

The three benchmark files above GitHub's 50 MB warning threshold are tracked with Git LFS:

```text
datasets/chainstore.txt
datasets/accidents.txt
datasets/kosarak.txt
```

After cloning the repository, install/initialize Git LFS and retrieve the actual files:

```bash
git lfs install
git lfs pull
```

Verify that they are present rather than LFS pointer files before running experiments.

## Threshold settings

The ten absolute minimum-utility settings used in the final threshold experiment are:

| Dataset | T10 | T9 | T8 | T7 | T6 | T5 | T4 | T3 | T2 | T1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Foodmart | 24,000 | 18,000 | 15,000 | 12,000 | 9,000 | 8,000 | 7,000 | 6,000 | 4,000 | 3,000 |
| Ecommerce | 746,000 | 596,000 | 447,000 | 298,000 | 224,000 | 186,000 | 180,000 | 175,000 | 170,000 | 165,000 |
| Retail | 8,900 | 7,700 | 6,900 | 6,100 | 5,300 | 4,500 | 3,700 | 3,000 | 2,200 | 1,500 |
| Fruithut | 262,000 | 209,000 | 157,000 | 105,000 | 79,000 | 65,000 | 52,000 | 39,000 | 26,000 | 13,000 |
| Accidents | 30,000,000 | 29,000,000 | 28,000,000 | 27,000,000 | 26,000,000 | 25,000,000 | 24,000,000 | 23,000,000 | 22,000,000 | 21,000,000 |
| Kosarak | 5,000,000 | 4,500,000 | 4,000,000 | 3,500,000 | 3,250,000 | 3,000,000 | 2,750,000 | 2,500,000 | 2,250,000 | 2,000,000 |
| Chainstore | 652,000 | 522,000 | 391,000 | 261,000 | 196,000 | 163,000 | 130,000 | 98,000 | 95,000 | 90,000 |
| Chicago Crimes | 79,000 | 64,000 | 48,000 | 32,000 | 24,000 | 20,000 | 16,000 | 12,000 | 8,000 | 4,000 |

T10 is the highest/easiest threshold and T1 is the lowest/hardest threshold.

## Scalability settings

Scalability uses:

```text
20%, 40%, 60%, 80%, 100%
```

of the valid transaction sequence, always taking the first `N` valid transactions.

The minimum utility is fixed at T4 for each dataset:

| Dataset | Scalability minUtil (T4) |
|---|---:|
| Foodmart | 7,000 |
| Ecommerce | 180,000 |
| Retail | 3,700 |
| Fruithut | 52,000 |
| Accidents | 24,000,000 |
| Kosarak | 2,750,000 |
| Chainstore | 130,000 |
| Chicago Crimes | 16,000 |

The 100% scalability task is therefore identical to the full-dataset T4 threshold task, and the final analysis reuses the same canonical execution.

## Files not included in the final benchmark

Earlier development work also considered Yoochoose and Liquor. They are not part of the final eight-dataset BDA benchmark and should not be included when reproducing the reported results.

The available Yoochoose preparation contained duplicate/malformed item occurrences, while the Liquor preparation used decimal utilities that did not conform to the common integer-utility protocol used for the final comparison.

## Provenance and redistribution note

These files are the exact benchmark copies used for the PA-HUIM experiments. The archived project materials supplied for this repository do not contain complete upstream source URLs and redistribution-license metadata for every dataset.

Accordingly, this document does **not** claim ownership of the original datasets or assert that every upstream dataset may be freely redistributed. Before making the repository public, the repository maintainer should verify the original source and redistribution terms for each dataset and add the appropriate source citations/licenses here.

If an upstream license does not permit redistribution, remove that dataset file from Git/Git LFS and replace it with acquisition/preparation instructions while retaining the SHA-256 checksum so users can verify that they obtained the same benchmark copy.
