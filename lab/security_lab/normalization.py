import base64
import binascii
import re
import unicodedata

ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}


def normalize_text(value: str) -> dict[str, object]:
    """Apply an idempotent normalization pass and retain forensic metadata."""
    original = value
    removed = [f"U+{ord(char):04X}" for char in value if char in ZERO_WIDTH]
    value = unicodedata.normalize("NFKC", value)
    value = "".join(char for char in value if char not in ZERO_WIDTH)
    value = re.sub(r"[\t\r\n ]+", " ", value).strip()
    return {"original": original, "normalized": value, "removed_codepoints": removed}


def decode_base64_once(value: str, max_output_bytes: int = 4096) -> str | None:
    """Decode one bounded layer only; never execute or recursively expand it."""
    compact = re.sub(r"\s+", "", value)
    if len(compact) < 8 or len(compact) % 4:
        return None
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(decoded) > max_output_bytes:
        return None
    try:
        return decoded.decode("utf-8")
    except UnicodeDecodeError:
        return None
