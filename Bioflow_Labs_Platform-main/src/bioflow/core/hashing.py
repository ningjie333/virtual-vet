import hashlib
import json
from typing import Any

# Normalize for proper hashing


def normalize_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

# Turn "JSON" -> string into 64-char hex -> string


def hash_json(obj: Any) -> str:
    s = normalize_json(obj).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


"""
JSON object              # Normalized
→ canonical string
→ UTF-8 bytes
→ 256-bit binary hash
→ 64-char hex string     # Proper python string

"""
