from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    tests = sorted((ROOT / "tests").glob("test_*.py"))
    if not tests:
        raise RuntimeError("no operational tests found")
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", *map(str, tests)], cwd=ROOT
    )


if __name__ == "__main__":
    raise SystemExit(main())
