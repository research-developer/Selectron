"""
Selectron Configuration

Environment variable handling and application directory management.
"""

import glob
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set, List


# Environment variable names
ENV_DEFAULT_APP = "SELECTRON_DEFAULT_APP"
ENV_DEFAULT_APP_DIR = "SELECTRON_DEFAULT_APP_DIR"
ENV_SEARCH_DIRS = "SELECTRON_SEARCH_DIRS"  # Colon-separated list

# Default search directories (will be expanded and deduplicated)
DEFAULT_SEARCH_DIRS = [
    "/Applications/",
    "~/Applications/",
    "/Applications/Setapp/",
    "/Applications/*/",  # Glob pattern for app containers
]

# Default port range for scanning
DEFAULT_PORT_RANGE = (9222, 9250)


class CaseInsensitivePathSet:
    """
    A set-like container for Paths that deduplicates case-insensitively.

    macOS filesystems are case-insensitive by default, so /Applications
    and /applications are the same directory.
    """

    def __init__(self):
        self._paths: Set[Path] = set()
        self._lower_strings: Set[str] = set()

    def add(self, path: Path) -> bool:
        """
        Add a path to the set.

        Returns:
            True if path was added, False if it was a duplicate
        """
        lower_str = str(path).lower()
        if lower_str in self._lower_strings:
            return False
        self._lower_strings.add(lower_str)
        self._paths.add(path)
        return True

    def __contains__(self, path: Path) -> bool:
        return str(path).lower() in self._lower_strings

    def __iter__(self):
        return iter(self._paths)

    def __len__(self):
        return len(self._paths)

    def __repr__(self):
        return f"CaseInsensitivePathSet({self._paths})"

    def to_set(self) -> Set[Path]:
        """Return a regular set of paths."""
        return self._paths.copy()


@dataclass
class SelectronConfig:
    """
    Global configuration for Selectron.

    Attributes:
        default_app: Default application name (from SELECTRON_DEFAULT_APP)
        search_dirs: Set of directories to search for applications
        sessions_file: Path to the sessions persistence file
        port_scan_range: Port range for scanning (start, end inclusive)
    """
    default_app: Optional[str] = None
    search_dirs: Set[Path] = field(default_factory=set)
    sessions_file: Path = field(
        default_factory=lambda: Path.home() / ".selectron" / "sessions.json"
    )
    port_scan_range: tuple = DEFAULT_PORT_RANGE

    @classmethod
    def from_environment(cls) -> "SelectronConfig":
        """
        Load configuration from environment variables.

        Environment Variables:
            SELECTRON_DEFAULT_APP: Default app name
            SELECTRON_DEFAULT_APP_DIR: First directory to search (prepended)
            SELECTRON_SEARCH_DIRS: Colon-separated list of additional directories
        """
        config = cls()

        # Load default app name
        config.default_app = os.environ.get(ENV_DEFAULT_APP)

        # Build search directories
        dirs_to_add: List[str] = []

        # First, add env-specified directory (takes priority)
        if env_dir := os.environ.get(ENV_DEFAULT_APP_DIR):
            dirs_to_add.append(env_dir)

        # Add any additional env-specified directories
        if env_dirs := os.environ.get(ENV_SEARCH_DIRS):
            dirs_to_add.extend(env_dirs.split(":"))

        # Add defaults
        dirs_to_add.extend(DEFAULT_SEARCH_DIRS)

        # Process and deduplicate
        config.search_dirs = cls._normalize_search_dirs(dirs_to_add)

        return config

    @staticmethod
    def _normalize_search_dirs(dirs: List[str]) -> Set[Path]:
        """
        Expand ~ and glob patterns, deduplicate case-insensitively.

        Args:
            dirs: List of directory paths (may include ~ and glob patterns)

        Returns:
            Set of normalized, deduplicated Path objects
        """
        path_set = CaseInsensitivePathSet()

        for d in dirs:
            # Expand ~ to home directory
            expanded = os.path.expanduser(d)

            if "*" in expanded or "?" in expanded or "[" in expanded:
                # Glob pattern - expand it
                for match in glob.glob(expanded):
                    path = Path(match)
                    if path.is_dir():
                        path_set.add(path.resolve())
            else:
                path = Path(expanded)
                if path.exists() and path.is_dir():
                    path_set.add(path.resolve())
                elif not path.exists():
                    # Still add non-existent paths (they might be created later)
                    path_set.add(path.resolve())

        return path_set.to_set()

    def get_ordered_search_dirs(self) -> List[Path]:
        """
        Get search directories in priority order.

        The SELECTRON_DEFAULT_APP_DIR is always first if set.
        """
        dirs = list(self.search_dirs)

        # Move the env-specified directory to front if it exists
        if env_dir := os.environ.get(ENV_DEFAULT_APP_DIR):
            env_path = Path(os.path.expanduser(env_dir)).resolve()
            if env_path in dirs:
                dirs.remove(env_path)
                dirs.insert(0, env_path)

        return dirs


# Global singleton
_config: Optional[SelectronConfig] = None


def get_config() -> SelectronConfig:
    """
    Get the global configuration singleton.

    Returns:
        SelectronConfig instance loaded from environment
    """
    global _config
    if _config is None:
        _config = SelectronConfig.from_environment()
    return _config


def reset_config() -> None:
    """
    Reset the global configuration singleton.

    Useful for testing or when environment variables change.
    """
    global _config
    _config = None


def set_config(config: SelectronConfig) -> None:
    """
    Set the global configuration singleton.

    Args:
        config: Configuration to use
    """
    global _config
    _config = config
