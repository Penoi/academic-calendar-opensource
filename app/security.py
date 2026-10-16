import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

SESSION_COOKIE = "session"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHasher()
# usado quando o email não existe, para o login levar o mesmo tempo nos dois casos
_DUMMY_HASH = _hasher.hash("senha-que-ninguem-usa")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token_for(session_token: str) -> str:
    """Token CSRF derivado da sessão: não precisa ser guardado em lugar nenhum."""
    return hmac.new(settings.secret_key.encode(), session_token.encode(), hashlib.sha256).hexdigest()


def csrf_is_valid(session_token: str, sent: str | None) -> bool:
    return sent is not None and hmac.compare_digest(csrf_token_for(session_token), sent)
