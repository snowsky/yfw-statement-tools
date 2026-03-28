"""
Backward-compatible plugin entry point.

When installed as a YFW plugin the repo root lands at api/plugins/statement_tools/.
Adding that directory to sys.path makes `plugin` and `shared` importable as
top-level packages in both standalone and plugin-mode contexts.
"""
import sys
from pathlib import Path

_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from plugin.api import register_plugin  # noqa: E402

__all__ = ["register_plugin"]
