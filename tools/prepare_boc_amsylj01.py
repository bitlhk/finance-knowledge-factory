"""Regenerate the fixed AMSYLJ01 source bundle."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from business_knowledge.boc_amsylj01 import write_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(
        "examples/business/customer-manager/amsylj01"))
    args = parser.parse_args()
    write_bundle(args.root / "sources", args.root.parent /
                 "boc-wealth-manager-test-set-v0.1.json", args.root / "generated")


if __name__ == "__main__":
    main()
