#!/usr/bin/env python3
"""SQLite online backup, checked restore, and explicit migration commands."""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.db import PortfolioStore

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("command",choices=["backup","restore","migrate"])
parser.add_argument("database",type=Path)
parser.add_argument("snapshot",type=Path,nargs="?")
parser.add_argument("--confirm-overwrite",action="store_true",help="Required for restore; stop app before restoring")
args=parser.parse_args()
if args.command=="migrate":
    store=PortfolioStore(args.database); store.engine.dispose()
    print("Schema migration complete."); raise SystemExit()
if args.snapshot is None:
    parser.error("snapshot is required")
if args.command=="backup":
    if args.snapshot.exists():
        parser.error("Refusing to overwrite an existing snapshot")
    args.snapshot.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(f"file:{args.database.resolve()}?mode=ro",uri=True) as source, sqlite3.connect(args.snapshot) as target:
        source.backup(target)
    args.snapshot.chmod(0o600)
    print("Backup created; protect this file as private portfolio data.")
else:
    if not args.confirm_overwrite:
        parser.error("Restore overwrites portfolio data; stop app and pass --confirm-overwrite")
    if Path(str(args.database)+"-wal").exists() or Path(str(args.database)+"-shm").exists():
        parser.error("Database WAL/SHM files exist; close all database connections before restoring")
    with sqlite3.connect(f"file:{args.snapshot.resolve()}?mode=ro",uri=True) as source:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            parser.error("Snapshot integrity check failed")
        versions=source.execute("SELECT version FROM schema_versions").fetchall()
        if versions != [(1,)]:
            parser.error("Unsupported snapshot schema")
        args.database.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.database.with_name(args.database.name+".restoring")
        if temporary.exists():
            parser.error("A previous .restoring file exists; inspect it before retrying")
        with sqlite3.connect(temporary) as target:
            source.backup(target)
        temporary.chmod(0o600)
        os.replace(temporary,args.database)
    print("Restore complete. Restart the application and verify owner access.")
