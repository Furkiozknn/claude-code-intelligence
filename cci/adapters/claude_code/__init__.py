"""Claude Code adaptoru (docs/PROVIDERS.md §4) - referans uygulama."""

from .adapter import SCHEMA_VERIFIED_AT, ClaudeCodeAdapter
from .paths import (config_dirs, credentials_path, find_transcripts, instance_for, projects_dir)

__all__ = [
    "SCHEMA_VERIFIED_AT", "ClaudeCodeAdapter",
    "config_dirs", "credentials_path", "find_transcripts", "instance_for", "projects_dir",
]
