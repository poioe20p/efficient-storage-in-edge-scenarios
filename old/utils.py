import hashlib
import os


def stable_hash_unit(text: str) -> float:
    """Return a stable pseudo-random float in (0, 1) for the given text."""
    if text is None:
        text = ""
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return (value + 1) / float(2**64 + 1)


def env_int(name: str, default: int) -> int:
    """Read an env var as int, falling back to default on missing/invalid values."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def env_float(name: str, default: float) -> float:
    """Read an env var as float, falling back to default on missing/invalid values."""
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(str(raw).strip())
    except Exception:
        return float(default)


def env_bool(name: str, default: bool) -> bool:
    """Read an env var as bool.

    Accepted false values: 0, false, no, off, n
    Accepted true values:  1, true, yes, on, y
    """

    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in ("0", "false", "no", "off", "n"):
        return False
    if value in ("1", "true", "yes", "on", "y"):
        return True
    return bool(default)