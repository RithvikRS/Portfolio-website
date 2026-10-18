#!/usr/bin/env python3
"""Create the private bind mount for the non-root Node container; never reset data."""
import os
from pathlib import Path

root = Path(__file__).resolve().parent.parent
directory = root / '.notes'
if os.getuid() != 1000 or os.getgid() != 1000:
    raise SystemExit('Run as the repository owner with UID/GID 1000 (the Node container user).')
if directory.is_symlink():
    raise SystemExit('Refusing a symlink for writing storage.')
directory.mkdir(mode=0o700, exist_ok=True)
if directory.stat().st_uid != 1000 or directory.stat().st_gid != 1000:
    raise SystemExit('Writing storage must belong to UID/GID 1000. Restore its ownership before deploying.')
directory.chmod(0o700)
print('Private writing storage is ready; existing entries are preserved.')
