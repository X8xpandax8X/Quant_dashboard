"""Export the real API contract without network requests or production credentials."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api import create_app
from app.config import Settings

with tempfile.TemporaryDirectory() as directory:
    application = create_app(Settings(mode="demo", storage_dir=Path(directory), _env_file=None))
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/openapi.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(application.openapi(), indent=2) + "\n")
    application.state.store.engine.dispose()
    print(destination)
