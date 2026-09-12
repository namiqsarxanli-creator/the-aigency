"""Lokal hesab, workspace və server-side sessiya təhlükəsizliyi."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_models import User, UserSession, Workspace, WorkspaceMember
from app.core import settings

SESSION_COOKIE = "agency_session"
SESSION_DAYS = 30
PBKDF2_ROUNDS = 310_000


@dataclass(frozen=True)
class AuthContext:
    user: User
    workspace: Workspace
    membership: WorkspaceMember


def is_platform_owner(context: AuthContext | None) -> bool:
    """İlk/legacy workspace platformanın öz idarəetmə hesabıdır.

    Sonradan yaradılan şirkətlər öz workspace-lərinin owner-i olsalar da platformanın daxili
    satış fabriki, xərc hesabatı və Control Room-na giriş əldə etmirlər.
    """
    return bool(
        context
        and context.workspace.slug == "legacy"
        and context.membership.role in {"owner", "admin", "presenter"}
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "workspace"


def unique_workspace_slug(db: Session, name: str) -> str:
    base = _slugify(name)
    slug = base
    counter = 2
    while db.query(Workspace).filter(Workspace.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def register_user(db: Session, email: str, full_name: str, company_name: str, password: str) -> AuthContext:
    email = email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise ValueError("Bu email artıq qeydiyyatdan keçib.")
    first_account = db.query(User).count() == 0
    user = User(email=email, full_name=full_name.strip(), password_hash=hash_password(password))
    workspace = db.query(Workspace).filter(Workspace.slug == "legacy").first() if first_account else None
    if workspace:
        workspace.name = company_name.strip()
    else:
        workspace = Workspace(name=company_name.strip(), slug=unique_workspace_slug(db, company_name))
        db.add(workspace)
    db.add(user)
    db.flush()
    membership = WorkspaceMember(user_id=user.id, workspace_id=workspace.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(user)
    db.refresh(workspace)
    db.refresh(membership)
    return AuthContext(user=user, workspace=workspace, membership=membership)


def authenticate(db: Session, email: str, password: str) -> AuthContext | None:
    user = db.query(User).filter(User.email == email.strip().lower(), User.is_active.is_(True)).first()
    if not user or not verify_password(password, user.password_hash):
        return None
    membership = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == user.id)
        .order_by(WorkspaceMember.id)
        .first()
    )
    if not membership:
        return None
    return AuthContext(user=user, workspace=membership.workspace, membership=membership)


def create_session(db: Session, context: AuthContext) -> str:
    raw_token = secrets.token_urlsafe(40)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db.add(UserSession(
        token_hash=token_hash,
        user_id=context.user.id,
        workspace_id=context.workspace.id,
        expires_at=_utcnow() + timedelta(days=SESSION_DAYS),
    ))
    db.commit()
    return raw_token


def revoke_session(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db.query(UserSession).filter(UserSession.token_hash == token_hash).delete()
    db.commit()


def context_from_token(raw_token: str | None, db: Session) -> AuthContext | None:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    session = db.query(UserSession).filter(UserSession.token_hash == token_hash).first()
    if not session or session.expires_at <= _utcnow() or not session.user.is_active:
        if session:
            db.delete(session)
            db.commit()
        return None
    membership = (
        db.query(WorkspaceMember)
        .filter(
            WorkspaceMember.user_id == session.user_id,
            WorkspaceMember.workspace_id == session.workspace_id,
        )
        .first()
    )
    if not membership:
        return None
    return AuthContext(user=session.user, workspace=session.workspace, membership=membership)


def context_from_request(request: Request, db: Session) -> AuthContext | None:
    return context_from_token(request.cookies.get(SESSION_COOKIE), db)


def require_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    context = context_from_request(request, db)
    if not context:
        raise HTTPException(status_code=401, detail="Hesaba daxil olun.")
    return context


def workspace_scope(
    request: Request,
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> int:
    """Brauzer sessiyasından workspace seçir; avtomasiya üçün yalnız konfiqurasiya edilmiş API key qəbul edir."""
    context = context_from_request(request, db)
    if context:
        return context.workspace.id
    if not settings.agency_api_key or not hmac.compare_digest(x_api_key or "", settings.agency_api_key):
        raise HTTPException(status_code=401, detail="Hesaba daxil olun və ya düzgün X-API-Key göndərin.")
    workspace = db.query(Workspace).filter(Workspace.slug == "legacy").first()
    if not workspace:
        workspace = db.query(Workspace).order_by(Workspace.id).first()
    if not workspace:
        raise HTTPException(status_code=503, detail="Workspace yaradılmayıb.")
    return workspace.id


def set_session_cookie(response, raw_token: str) -> None:
    secure = settings.cookie_secure or settings.public_base_url.startswith("https://")
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
