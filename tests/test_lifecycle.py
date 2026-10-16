import os
from pathlib import Path
import subprocess
import sys


def test_application_exits_cleanly_after_native_window_smoke(tmp_path):
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["XDG_DATA_HOME"] = str(tmp_path)
    root = Path(__file__).resolve().parent.parent
    result = subprocess.run([sys.executable, str(root / "run_pet.py"), "--smoke-test"],
                            cwd=root, env=environment, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
