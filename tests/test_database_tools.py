import sqlite3
import subprocess
import sys
from pathlib import Path

from app.db import PortfolioStore

SCRIPT=Path(__file__).resolve().parents[1]/"scripts/database.py"


def test_backup_and_restore_round_trip(tmp_path):
    database=tmp_path/"original.sqlite3"
    snapshot=tmp_path/"private-snapshot.sqlite3"
    restored=tmp_path/"restored.sqlite3"
    store=PortfolioStore(database)
    saved=store.create("owner-one","Protected basket",[{"symbol":"MSFT","weight_bps":10000}])
    subprocess.run([sys.executable,str(SCRIPT),"backup",str(database),str(snapshot)],check=True,capture_output=True)
    assert snapshot.stat().st_mode & 0o077 == 0
    refused=subprocess.run([sys.executable,str(SCRIPT),"restore",str(restored),str(snapshot)],capture_output=True)
    assert refused.returncode != 0 and not restored.exists()
    subprocess.run([sys.executable,str(SCRIPT),"restore",str(restored),str(snapshot),"--confirm-overwrite"],check=True,capture_output=True)
    target=PortfolioStore(restored)
    assert target.get("owner-one",saved["id"])["name"]=="Protected basket"
    assert target.list("owner-two")==[]
    target.engine.dispose();store.engine.dispose()
