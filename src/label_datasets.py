"""Create provenance-labelled copies of the project's housing datasets."""

from pathlib import Path

from src.source_labels import label_csv


FILES = [
    "data/processed/housing_indices_clean_v2.csv",
    "data/processed/macro_features.csv",
    "data/processed/district_price_sample.csv",
    "data/processed/beijing_district_transactions.csv",
    "data/processed/beijing_official_district_secondhand_2025_10.csv",
]


def main() -> None:
    for name in FILES:
        input_path = Path(name)
        output_path = input_path.with_name(input_path.stem + "_labeled.csv")
        print(f"{output_path}: {label_csv(input_path, output_path)} rows")


if __name__ == "__main__":
    main()
