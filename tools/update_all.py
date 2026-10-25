"""Refresh everything from the live channel.

Usage: python tools/update_all.py            (fetch new posts + rebuild)
       python tools/update_all.py --full     (re-read the whole channel + rebuild)
       python tools/update_all.py --no-scrape (rebuild from the saved posts only)
"""
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = [sys.executable, "-X", "utf8"]

steps = []
if "--no-scrape" not in sys.argv:
    steps.append(["tools/scrape.py", "reyad_elganna", "data/posts.json"] + (["--full"] if "--full" in sys.argv else []))
steps += [["tools/classify.py"], ["tools/posters.py"], ["tools/build_index.py"], ["tools/build_site.py"]]

for s in steps:
    print("▶", " ".join(s), flush=True)
    subprocess.run(PY + s, cwd=ROOT, check=True)
print("✔ done")
