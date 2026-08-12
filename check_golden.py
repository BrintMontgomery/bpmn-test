"""Regenerate the existing BPMN diagrams and compare them byte-for-byte."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
GENERATORS = {
    "generate_bpmn.py": ("OFC-001.bpmn", "OFC-001.mmd"),
    "generate_bpmn_ofc004.py": ("OFC-004.bpmn",),
}


def main() -> int:
    mismatches: list[str] = []

    with tempfile.TemporaryDirectory(prefix="bpmn-golden-") as temp_dir:
        work = Path(temp_dir)
        for generator, outputs in GENERATORS.items():
            shutil.copy2(ROOT / generator, work / generator)
            subprocess.run(
                [sys.executable, generator],
                cwd=work,
                check=True,
            )

            for output in outputs:
                expected = ROOT / output
                actual = work / output
                if not actual.exists():
                    mismatches.append(f"{output}: generator did not produce it")
                elif not expected.exists():
                    mismatches.append(f"{output}: golden file is missing")
                elif actual.read_bytes() != expected.read_bytes():
                    mismatches.append(f"{output}: bytes differ")

    if mismatches:
        print("golden check failed:")
        for mismatch in mismatches:
            print(f"  - {mismatch}")
        return 1

    print("golden files match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
