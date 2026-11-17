"""Collecte GDELT horaire : python run_gdelt.py (sans pandas, démarrage rapide)"""
import json
import pathlib

import yaml

from radar import gdelt

root = pathlib.Path(__file__).parent
cfg = yaml.safe_load((root / "config.yaml").read_text())
print(json.dumps(gdelt.collect_hourly(cfg, root), ensure_ascii=False))
