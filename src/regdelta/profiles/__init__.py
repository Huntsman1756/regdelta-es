"""Installed source profiles — the composition manifest.

Importing this package registers every installed profile with the
core registry (``regdelta.profile``). Profile packages hold
source-specific data and boundary code; nothing here is imported
by the core at module load time — the registry resolves profiles
lazily at first use.
"""

from . import bde  # noqa: F401
