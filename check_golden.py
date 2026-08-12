"""Regenerate the migrated BPMN diagrams and validate every output."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).parent
IR_FILES = ("OFC-001.ir.json", "OFC-004.ir.json")
OUTPUTS = ("OFC-001.bpmn", "OFC-004.bpmn")
PIPELINE_FILES = {
    "bpmn_engine.py",
    "decomposition.py",
    "geometry.py",
    "ir.py",
    "ir_schema.json",
    "ir_to_bpmn.py",
    "validate_bpmn.py",
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bpmn-golden-") as temp_dir:
        work = Path(temp_dir)
        for filename in PIPELINE_FILES | set(IR_FILES):
            shutil.copy2(ROOT / filename, work / filename)
        subprocess.run(
            [sys.executable, "ir_to_bpmn.py", *IR_FILES, "-o", str(work)],
            cwd=work,
            check=True,
        )
        for output in OUTPUTS:
            actual = work / output
            if not actual.exists():
                print(f"{output}: IR pipeline did not produce it")
                return 1
            subprocess.run(
                [sys.executable, "validate_bpmn.py", output],
                cwd=work,
                check=True,
            )

    print("generated BPMN outputs passed validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
