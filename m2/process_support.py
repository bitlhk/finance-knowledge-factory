"""Local process provenance helpers; no transport or credential dependencies."""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def record(path, value):
    fd, temporary = tempfile.mkstemp(prefix='.runtime-record-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)  # Atomic visibility and no overwrite, including symlinks.
    finally:
        os.unlink(temporary)


def code_identity():
    root = Path(__file__).resolve().parents[1]
    try:
        commit = subprocess.run(['git','rev-parse','HEAD'],cwd=root,check=True,
            capture_output=True,text=True,timeout=5).stdout.strip()
        status = subprocess.run(['git','status','--porcelain'],cwd=root,check=True,
            capture_output=True,text=True,timeout=5).stdout
        return {'commit':commit,'dirty':bool(status)}
    except (OSError,subprocess.SubprocessError):
        return {'commit':None,'dirty':None}
