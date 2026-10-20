"""
WanderWall - Pairing Code Management.

Generates and validates pairing codes for device enrollment.
Codes are 6 alphanumeric characters (36^6 = 2.17B combinations).
"""

import re
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.config.settings import DemoConfig

# Code format: 6 alphanumeric, case-insensitive
CODE_LENGTH = 6
CODE_CHARS = string.ascii_uppercase + string.digits  # 36 chars

# Security limits
CODE_EXPIRY_MINUTES = 5
MAX_ATTEMPTS = 3
MAX_CODES_PER_HOUR = 3


class PairingCode(BaseModel):
    """An active pairing code."""
    code: str
    created_at: datetime
    expires_at: datetime
    attempts: int = 0


# In-memory store for active codes (single Pi, single process)
# In production, this could be persisted to a file
_active_codes: dict[str, PairingCode] = {}
_generation_timestamps: list[datetime] = []


def generate_pairing_code() -> Optional[PairingCode]:
    """
    Generate a new pairing code.

    Returns:
        PairingCode if successful, None if rate limited

    Rate limit: 3 codes per hour
    """
    now = datetime.now(timezone.utc)

    # Clean up old timestamps
    cutoff = now - timedelta(hours=1)
    _generation_timestamps[:] = [ts for ts in _generation_timestamps if ts > cutoff]

    # Check rate limit
    if len(_generation_timestamps) >= MAX_CODES_PER_HOUR:
        return None

    # Generate code
    code = "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))

    # Format as ABC-XYZ for readability
    formatted_code = f"{code[:3]}-{code[3:]}"

    pairing_code = PairingCode(
        code=formatted_code,
        created_at=now,
        expires_at=now + timedelta(minutes=CODE_EXPIRY_MINUTES),
    )

    # Store code and timestamp
    _active_codes[formatted_code.upper()] = pairing_code
    _generation_timestamps.append(now)

    return pairing_code


def verify_pairing_code(code: str) -> bool:
    """
    Verify a pairing code.

    Args:
        code: The code to verify (case-insensitive)

    Returns:
        True if code is valid

    Side effects:
        - Increments attempt counter
        - Invalidates code after 3 failed attempts
        - Invalidates code on success (single use)
    """
    normalized = code.upper().strip()
    now = datetime.now(timezone.utc)

    if normalized not in _active_codes:
        return False

    pairing_code = _active_codes[normalized]

    # Check expiry
    if now > pairing_code.expires_at:
        del _active_codes[normalized]
        return False

    # Check attempts
    if pairing_code.attempts >= MAX_ATTEMPTS:
        del _active_codes[normalized]
        return False

    # Increment attempts
    pairing_code.attempts += 1

    # On success, invalidate code (single use)
    del _active_codes[normalized]
    return True


def get_active_code() -> Optional[PairingCode]:
    """
    Get the currently active pairing code, if any.

    Cleans up expired codes.
    """
    now = datetime.now(timezone.utc)

    # Clean up expired codes
    expired = [
        code for code, pc in _active_codes.items()
        if now > pc.expires_at or pc.attempts >= MAX_ATTEMPTS
    ]
    for code in expired:
        del _active_codes[code]

    # Return most recent active code
    if _active_codes:
        return max(_active_codes.values(), key=lambda pc: pc.created_at)
    return None


DEMO_CODE_RE = re.compile(r"^[A-Z0-9]{3}-[A-Z0-9]{3}$")


def _new_code() -> str:
    """Return a random code formatted as ABC-XYZ."""
    code = "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))
    return f"{code[:3]}-{code[3:]}"


def generate_demo_codes() -> tuple[str, str]:
    """Return a new (admin_code, contributor_code) pair; the two always differ."""
    admin_code = _new_code()
    contributor_code = _new_code()
    while contributor_code == admin_code:
        contributor_code = _new_code()
    return admin_code, contributor_code


def _same_code(a: str, b: str) -> bool:
    """Constant-time comparison of two normalized codes; invalid stored codes never match."""
    b = b.upper().strip()
    if not DEMO_CODE_RE.match(b):
        return False
    return secrets.compare_digest(a.encode(), b.encode())


def match_demo_code(code: str, demo: "DemoConfig", now: Optional[datetime] = None) -> Optional[str]:
    """
    Check a code against the demo codes (PL-015).

    Args:
        code: The code the phone sent (case-insensitive)
        demo: The frame's demo settings
        now: Current time (for tests)

    Returns:
        "admin" or "contributor" for a live demo code, "expired" for a demo code this
        frame issued that no longer works, or None when it isn't a demo code
        (or demo mode isn't allowed on this frame).
    """
    if not demo.allowed:
        return None
    normalized = code.upper().strip()
    now = now or datetime.now(timezone.utc)
    live = demo.enabled and demo.expires_at is not None and now < demo.expires_at

    for stored, role in ((demo.admin_code, "admin"), (demo.contributor_code, "contributor")):
        if _same_code(normalized, stored):
            return role if live else "expired"
    if any(_same_code(normalized, old) for old in demo.previous_codes):
        return "expired"
    return None


def invalidate_all_codes():
    """Invalidate all active pairing codes and reset rate limit counter."""
    _active_codes.clear()
    _generation_timestamps.clear()
