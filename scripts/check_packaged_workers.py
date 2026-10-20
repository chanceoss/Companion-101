"""Exercise JSON pipes in a windowed executable without OAuth/audio/model access."""

import json
from pathlib import Path
import subprocess
import sys


def main():
    executable = Path(sys.argv[1]).resolve()
    for worker in ("voice_worker.py", "google_worker.py"):
        result = subprocess.run(
            [str(executable), "--integration-worker", worker, "protocol_test"],
            input="{}",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"{worker}: packaged worker exited with code {result.returncode}."
            )
        try:
            response = json.loads(result.stdout)
        except ValueError:
            raise RuntimeError(
                f"{worker}: packaged JSON pipes are unavailable."
            ) from None
        if not response.get("ok") or not response.get("result", {}).get("ready"):
            raise RuntimeError(f"{worker}: optional build dependencies are missing.")
        print(worker + ": packaged protocol passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
