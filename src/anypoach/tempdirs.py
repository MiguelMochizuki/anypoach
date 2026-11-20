"""Private temporary directories named like the Swift app's (`anypoach-xxxxxx`), so storage cleanup can recognize them."""
import os
import secrets
import string
import tempfile
from pathlib import Path

_ALPHABET = string.ascii_letters + string.digits


def make_temp_dir(prefix: str = "anypoach-") -> Path:
    while True:
        path = Path(tempfile.gettempdir()) / (prefix + "".join(secrets.choice(_ALPHABET) for _ in range(6)))
        try:
            os.mkdir(path, 0o700)
            return path
        except FileExistsError:
            continue
