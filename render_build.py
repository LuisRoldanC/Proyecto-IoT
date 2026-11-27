import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PUBLISH_DIR = ROOT / "public"


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [sys.executable, str(ROOT / "sim_qos_qoe.py")],
            cwd=temp_dir,
            check=True,
        )

        generated_results = Path(temp_dir) / "results"
        publish_results = PUBLISH_DIR / "results"
        publish_results.mkdir(parents=True, exist_ok=True)

        for filename in ("simulation_summary.json", "simulation_summary.csv"):
            shutil.copy2(generated_results / filename, publish_results / filename)

    for filename in ("dashboard.html", "dashboard_img.png", "dashboard_img2.png"):
        shutil.copy2(ROOT / filename, PUBLISH_DIR / filename)


if __name__ == "__main__":
    main()
