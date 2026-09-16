#!/usr/bin/env python3
"""Optional read-only provider smoke checks; outputs metadata, never credentials."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from data_engine.service import DataService

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--live",action="store_true",help="Fetch public Yahoo/FRED data in local research mode")
args=parser.parse_args()
service=DataService(Path(".state/smoke-cache"),"research" if args.live else "demo")
for symbol in ["MSFT","^GSPC","^N225","^KS200","^SET.BK"]:
    history=service.get_history(symbol,"1Y")
    print(json.dumps({"symbol":symbol, "status":history.meta["status"],"count":len(history.frame),"as_of":history.meta["as_of"],"notes":history.meta["notes"]}),flush=True)
fundamentals=service.get_fundamentals("MSFT")
print(json.dumps({"fundamentals":fundamentals["meta"]["status"],"quarters":len(fundamentals["quarters"]),"estimate_available":fundamentals["estimate"] is not None,"notes":fundamentals["meta"]["notes"]}),flush=True)
rate=service.risk_free_rate()
print(json.dumps({"risk_free_status":rate["meta"]["status"],"observation":rate["date"]}),flush=True)
