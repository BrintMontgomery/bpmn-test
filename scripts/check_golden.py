"""Regenerate the migrated BPMN diagrams and validate every output."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "src"
IR_DIR = ROOT / "examples" / "ir"
IR_FILES = ("OFC-001.ir.json", "OFC-004.ir.json")
OUTPUTS = ("OFC-001.bpmn", "OFC-004.bpmn")
def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bpmn-golden-") as temp_dir:
        work = Path(temp_dir)
        subprocess.run(
            [sys.executable, str(SOURCE_DIR / "ir_to_bpmn.py"),
             *(str(IR_DIR / filename) for filename in IR_FILES), "-o", str(work)],
            cwd=ROOT,
            check=True,
        )
        for output in OUTPUTS:
            actual = work / output
            if not actual.exists():
                print(f"{output}: IR pipeline did not produce it")
                return 1
            subprocess.run(
                [sys.executable, str(SOURCE_DIR / "validate_bpmn.py"), str(actual)],
                cwd=ROOT,
                check=True,
            )

    print("generated BPMN outputs passed validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
