from pathlib import Path
from urllib.parse import urlparse
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QS_", env_file=".env", extra="ignore")
    mode: Literal["demo", "research", "production"] = "production"
    storage_dir: Path = Path(".state/production")
    public_origin: str = "http://127.0.0.1:5173"
    backend: Literal["legacy", "supabase"] = "legacy"
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    supabase_market_key: str = ""
    csrf_secret: str = ""
    proxy_secret: str = ""
    allowed_emails: str = ""
    data_rights_confirmed: bool = False
    session_max_age: int = 28800

    def check(self):
        if self.backend == "supabase":
            parsed = urlparse(self.supabase_url)
            local = parsed.hostname in {"127.0.0.1", "localhost"}
            if (not parsed.hostname or parsed.username or parsed.password or parsed.query
                    or parsed.fragment or parsed.path not in ("", "/")
                    or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))):
                raise RuntimeError("Supabase requires a trusted HTTPS project URL or local test URL")
            # New publishable keys cannot bypass RLS. Legacy JWT API keys are
            # deliberately not accepted on the private user-data connection.
            if not self.supabase_publishable_key.startswith("sb_publishable_"):
                raise RuntimeError("User data requires a Supabase publishable key, never a secret/service key")
            if len(self.csrf_secret) < 32 or not self.email_allowlist:
                raise RuntimeError("Supabase requires a CSRF secret and explicit email allowlist")
            if self.mode == "demo":
                raise RuntimeError("Demo is local-only; select research for Supabase")
        if self.mode != "demo":
            if self.backend == "legacy" and (len(self.proxy_secret) < 32 or not self.email_allowlist):
                raise RuntimeError("Research/production requires a proxy secret and email allowlist")
            if not self.public_origin.startswith("https://"):
                raise RuntimeError("Research/production requires HTTPS")
        if self.mode == "production" and not self.data_rights_confirmed:
            raise RuntimeError("Shared live deployment requires confirmed market-data use rights")

    @property
    def email_allowlist(self) -> set[str]:
        return {s.strip().lower() for s in self.allowed_emails.split(",") if s.strip()}
