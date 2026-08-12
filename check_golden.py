"""Regenerate the BPMN diagrams and validate every generated output."""

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
SHARED_MODEL_FILES = {
    "ofc001_model.py",
}
SHARED_ENGINE_FILES = {
    "geometry.py",
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="bpmn-golden-") as temp_dir:
        work = Path(temp_dir)
        shutil.copy2(ROOT / "bpmn_engine.py", work / "bpmn_engine.py")
        shutil.copy2(ROOT / "validate_bpmn.py", work / "validate_bpmn.py")
        for engine_file in SHARED_ENGINE_FILES:
            shutil.copy2(ROOT / engine_file, work / engine_file)
        for model_file in SHARED_MODEL_FILES:
            shutil.copy2(ROOT / model_file, work / model_file)
        for generator, outputs in GENERATORS.items():
            shutil.copy2(ROOT / generator, work / generator)
            subprocess.run(
                [sys.executable, generator],
                cwd=work,
                check=True,
            )

            for output in outputs:
                actual = work / output
                if not actual.exists():
                    print(f"{output}: generator did not produce it")
                    return 1
                if actual.suffix != ".bpmn":
                    continue
                subprocess.run(
                    [sys.executable, "validate_bpmn.py", output],
                    cwd=work,
                    check=True,
                )

    print("generated BPMN outputs passed validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
