"""Read only backend generation settings; never expose credentials to the UI."""

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / '.env'
ALLOWED = {'ALETHIA_LLM_PROVIDER', 'GEMINI_API_KEY', 'GEMINI_MODEL'}


def settings():
    values = {}
    if ENV_PATH.exists():
        if ENV_PATH.stat().st_size > 16384:
            raise ValueError('The backend .env file exceeds its 16 KiB limit.')
        for line in ENV_PATH.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            name,value = line.split('=',1)
            name,value = name.strip(),value.strip()
            if name not in ALLOWED:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            values[name] = value
    for name in ALLOWED:
        if name in os.environ:
            values[name] = os.environ[name]
    return values
