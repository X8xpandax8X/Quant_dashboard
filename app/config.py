from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="QS_", env_file=".env", extra="ignore")
    mode: Literal["demo", "research", "production"] = "production"
    storage_dir: Path = Path(".state/production")
    public_origin: str = "http://127.0.0.1:5173"
    proxy_secret: str = ""
    allowed_emails: str = ""
    data_rights_confirmed: bool = False
    session_max_age: int = 28800

    def check(self):
        if self.mode != "demo":
            if len(self.proxy_secret) < 32 or not self.email_allowlist:
                raise RuntimeError("Research/production requires a proxy secret and email allowlist")
            if not self.public_origin.startswith("https://"):
                raise RuntimeError("Research/production requires HTTPS")
        if self.mode == "production" and not self.data_rights_confirmed:
            raise RuntimeError("Shared live deployment requires confirmed market-data use rights")

    @property
    def email_allowlist(self) -> set[str]:
        return {s.strip().lower() for s in self.allowed_emails.split(",") if s.strip()}
