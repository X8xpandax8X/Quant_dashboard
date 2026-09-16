import hashlib
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE = "qs_demo_session"


def setup_secret(settings):
    if settings.mode != "demo":
        return settings.proxy_secret
    path = settings.storage_dir / ".session-key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        try:
            with path.open("x") as f:
                path.chmod(0o600)
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    return path.read_text().strip()


def serializer(request):
    return URLSafeTimedSerializer(request.app.state.auth_secret, salt="quant-stock-demo-v1")


def csrf_token(request, user):
    return hmac.new(request.app.state.auth_secret.encode(), ("csrf:" + user["id"]).encode(), hashlib.sha256).hexdigest()


def current_user(request: Request):
    settings = request.app.state.settings
    if settings.mode == "demo":
        try:
            user = serializer(request).loads(request.cookies.get(COOKIE, ""), max_age=settings.session_max_age)
        except (BadSignature, SignatureExpired):
            raise HTTPException(401, "Sign in to continue")
        if user.get("id") != "demo-researcher":
            raise HTTPException(401, "Invalid session")
    else:
        supplied = request.headers.get("x-proxy-secret", "")
        if not hmac.compare_digest(supplied, settings.proxy_secret):
            raise HTTPException(401, "Sign in to continue")
        subject = request.headers.get("x-auth-user", "")
        email = request.headers.get("x-auth-email", "").strip().lower()
        if not subject or len(subject) > 255 or email not in settings.email_allowlist:
            raise HTTPException(403, "This account is not on the team allowlist")
        user = {"id": hashlib.sha256(("google:" + subject).encode()).hexdigest(), "email": email, "name": email.split("@")[0]}
    request.app.state.store.remember_user(user)
    return user


def require_csrf(request: Request):
    user = current_user(request)
    token = request.headers.get("x-csrf-token", "")
    if not hmac.compare_digest(token, csrf_token(request, user)):
        raise HTTPException(403, "Security token expired. Refresh and retry.")
    origin = request.headers.get("origin", "")
    if origin != request.app.state.settings.public_origin.rstrip("/"):
        raise HTTPException(403, "Request origin is not allowed")
    return user
