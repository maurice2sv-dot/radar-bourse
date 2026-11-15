"""Radar bourse : python run.py [--mode demo|live] [--no-replay]"""
import argparse
import pathlib

import yaml

from radar import brief, dashboard, pipeline

ap = argparse.ArgumentParser()
ap.add_argument("--config", default="config.yaml")
ap.add_argument("--mode", choices=["demo", "live"])
ap.add_argument("--no-replay", action="store_true")
a = ap.parse_args()
root = pathlib.Path(__file__).parent
cfg = yaml.safe_load((root / a.config).read_text())
if a.mode:
    cfg["mode"] = a.mode
rep = pipeline.run(cfg, root, do_replay=not a.no_replay)
dashboard.render(rep, root / "dashboard.html")
daily = brief.generate(rep, root / "data")
print("\n".join(daily))
print("journal d'exécution :", rep["log"])
