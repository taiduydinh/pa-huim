from pathlib import Path

DATASET_PERCENTAGES = {
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


def read_total_database_utility(path: Path) -> int:
    total_utility = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            if line.startswith("#") or line.startswith("%") or line.startswith("@"):
                continue

            parts = line.split(":")

            if len(parts) < 2:
                continue

            try:
                transaction_utility = int(float(parts[1].strip()))
                total_utility += transaction_utility
            except ValueError:
                continue

    return total_utility


def find_dataset_file(folder: Path, dataset_name: str) -> Path | None:
    candidates = [
        folder / dataset_name,
        folder / f"{dataset_name}.txt",
        folder / f"{dataset_name}.dat",
        folder / f"{dataset_name}.csv",
    ]

    for path in candidates:
        if path.exists() and path.is_file():
            return path

    matches = list(folder.glob(dataset_name + ".*"))

    if matches:
        return matches[0]

    return None


def main():
    folder = Path(__file__).resolve().parent

    print(f"Searching datasets in: {folder}")
    print()

    for dataset_name, percentage in DATASET_PERCENTAGES.items():
        path = find_dataset_file(folder, dataset_name)

        if path is None:
            print(f"{dataset_name:15s} file not found")
            continue

        total_utility = read_total_database_utility(path)
        min_utility = round(total_utility * percentage / 100)

        print(
            f"{dataset_name:15s} "
            f"file={path.name:25s} "
            f"total_utility={total_utility:<15d} "
            f"percentage={percentage:<8g}% "
            f"min_utility={min_utility}"
        )


if __name__ == "__main__":
    main()