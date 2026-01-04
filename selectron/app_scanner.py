"""
Selectron App Scanner

Scans directories for installed Electron applications and builds an app registry.
"""

import glob
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import get_config, DEFAULT_SEARCH_DIRS


@dataclass
class ElectronApp:
    """
    Represents a discovered Electron application.

    Attributes:
        name: Application name (without .app suffix)
        app_bundle: Path to the .app bundle
        binary: Path to the main executable
        electron_framework: Path to the Electron Framework
        chrome_version: Embedded Chrome version (if detected)
        electron_version: Embedded Electron version (if detected)
        bundle_id: macOS bundle identifier
        version: App version string
        discovered_at: When this app was discovered
        metadata: Additional metadata
    """
    name: str
    app_bundle: Path
    binary: Path
    electron_framework: Path
    chrome_version: Optional[str] = None
    electron_version: Optional[str] = None
    bundle_id: Optional[str] = None
    version: Optional[str] = None
    discovered_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON persistence."""
        return {
            "name": self.name,
            "app_bundle": str(self.app_bundle),
            "binary": str(self.binary),
            "electron_framework": str(self.electron_framework),
            "chrome_version": self.chrome_version,
            "electron_version": self.electron_version,
            "bundle_id": self.bundle_id,
            "version": self.version,
            "discovered_at": self.discovered_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ElectronApp":
        """Deserialize from dictionary."""
        return cls(
            name=d["name"],
            app_bundle=Path(d["app_bundle"]),
            binary=Path(d["binary"]),
            electron_framework=Path(d["electron_framework"]),
            chrome_version=d.get("chrome_version"),
            electron_version=d.get("electron_version"),
            bundle_id=d.get("bundle_id"),
            version=d.get("version"),
            discovered_at=datetime.fromisoformat(d["discovered_at"]) if d.get("discovered_at") else datetime.now(),
            metadata=d.get("metadata", {}),
        )

    def __repr__(self) -> str:
        chrome = f", Chrome {self.chrome_version}" if self.chrome_version else ""
        return f"ElectronApp({self.name}{chrome})"


def is_electron_app(app_path: Path) -> bool:
    """
    Check if an app bundle is an Electron app.

    Args:
        app_path: Path to the .app bundle

    Returns:
        True if the app contains Electron Framework
    """
    framework_path = (
        app_path / "Contents" / "Frameworks" /
        "Electron Framework.framework" / "Versions" / "A" / "Electron Framework"
    )
    return framework_path.exists()


def get_app_info(app_path: Path) -> Optional[Dict[str, Any]]:
    """
    Get Info.plist data from an app bundle.

    Args:
        app_path: Path to the .app bundle

    Returns:
        Dict with bundle info, or None if not readable
    """
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return None

    try:
        # Use plutil to convert plist to JSON
        result = subprocess.run(
            ["plutil", "-convert", "json", "-o", "-", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass

    return None


def get_chrome_electron_version(framework_path: Path) -> tuple:
    """
    Extract Chrome and Electron versions from the Electron Framework binary.

    Args:
        framework_path: Path to the Electron Framework binary

    Returns:
        Tuple of (chrome_version, electron_version), either may be None
    """
    if not framework_path.exists():
        return (None, None)

    try:
        result = subprocess.run(
            ["strings", str(framework_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        chrome_version = None
        electron_version = None

        # Look for pattern like "Chrome/138.0.7204.251 Electron/37.10.3"
        match = re.search(
            r'Chrome/(\d+\.\d+\.\d+\.\d+)\s+Electron/(\d+\.\d+\.\d+)',
            result.stdout
        )
        if match:
            chrome_version = match.group(1)
            electron_version = match.group(2)

        return (chrome_version, electron_version)

    except subprocess.TimeoutExpired:
        return (None, None)


def scan_app(app_path: Path) -> Optional[ElectronApp]:
    """
    Scan a single app bundle and return ElectronApp if it's an Electron app.

    Args:
        app_path: Path to the .app bundle

    Returns:
        ElectronApp if it's an Electron app, None otherwise
    """
    if not app_path.is_dir() or not app_path.suffix == ".app":
        return None

    if not is_electron_app(app_path):
        return None

    name = app_path.stem
    framework_path = (
        app_path / "Contents" / "Frameworks" /
        "Electron Framework.framework" / "Versions" / "A" / "Electron Framework"
    )

    # Get binary path - usually same as app name, but check Info.plist
    binary_name = name
    info = get_app_info(app_path)
    if info:
        binary_name = info.get("CFBundleExecutable", name)

    binary_path = app_path / "Contents" / "MacOS" / binary_name

    # Get Chrome/Electron versions
    chrome_version, electron_version = get_chrome_electron_version(framework_path)

    return ElectronApp(
        name=name,
        app_bundle=app_path,
        binary=binary_path,
        electron_framework=framework_path,
        chrome_version=chrome_version,
        electron_version=electron_version,
        bundle_id=info.get("CFBundleIdentifier") if info else None,
        version=info.get("CFBundleShortVersionString") if info else None,
        metadata={
            "bundle_name": info.get("CFBundleName") if info else None,
            "min_os_version": info.get("LSMinimumSystemVersion") if info else None,
        },
    )


def scan_directory(
    directory: Path,
    recursive: bool = False,
    max_depth: int = 1,
) -> List[ElectronApp]:
    """
    Scan a directory for Electron apps.

    Args:
        directory: Directory to scan
        recursive: Whether to scan subdirectories
        max_depth: Maximum recursion depth (only used if recursive=True)

    Returns:
        List of discovered ElectronApp instances
    """
    apps = []

    if not directory.exists():
        return apps

    # Find all .app bundles
    if recursive:
        pattern = str(directory / "**" / "*.app")
        app_paths = [Path(p) for p in glob.glob(pattern, recursive=True)]
        # Filter by depth
        app_paths = [
            p for p in app_paths
            if len(p.relative_to(directory).parts) <= max_depth + 1
        ]
    else:
        app_paths = list(directory.glob("*.app"))

    for app_path in app_paths:
        if app := scan_app(app_path):
            apps.append(app)

    return apps


def scan_all_directories(
    directories: Optional[List[Path]] = None,
    parallel: bool = True,
    max_workers: int = 4,
) -> List[ElectronApp]:
    """
    Scan multiple directories for Electron apps.

    Args:
        directories: Directories to scan (uses config defaults if None)
        parallel: Whether to scan directories in parallel
        max_workers: Number of parallel workers

    Returns:
        List of all discovered ElectronApp instances
    """
    if directories is None:
        # Use default search directories, expanding globs
        directories = []
        for d in DEFAULT_SEARCH_DIRS:
            expanded = os.path.expanduser(d)
            if "*" in expanded:
                directories.extend(Path(p) for p in glob.glob(expanded) if Path(p).is_dir())
            else:
                path = Path(expanded)
                if path.exists():
                    directories.append(path)

    # Deduplicate
    seen = set()
    unique_dirs = []
    for d in directories:
        resolved = d.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique_dirs.append(resolved)

    all_apps = []

    if parallel and len(unique_dirs) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(scan_directory, d): d for d in unique_dirs}
            for future in as_completed(futures):
                try:
                    apps = future.result()
                    all_apps.extend(apps)
                except Exception as e:
                    print(f"Error scanning {futures[future]}: {e}")
    else:
        for d in unique_dirs:
            all_apps.extend(scan_directory(d))

    # Deduplicate apps by bundle path
    seen_bundles = set()
    unique_apps = []
    for app in all_apps:
        if app.app_bundle not in seen_bundles:
            seen_bundles.add(app.app_bundle)
            unique_apps.append(app)

    return unique_apps


class AppRegistry:
    """
    Registry of discovered Electron applications.

    Persists to ~/.selectron/apps.json for fast lookup.

    Example:
        registry = AppRegistry()
        registry.refresh()  # Scan for apps

        for app in registry.all_apps():
            print(f"{app.name}: Chrome {app.chrome_version}")

        claude = registry.get_by_name("Claude")
    """

    def __init__(self, persistence_path: Optional[Path] = None):
        """
        Initialize the app registry.

        Args:
            persistence_path: Path to save registry (defaults to ~/.selectron/apps.json)
        """
        self._apps: Dict[str, ElectronApp] = {}  # name -> ElectronApp
        self._persistence_path = persistence_path or (
            Path.home() / ".selectron" / "apps.json"
        )
        self._last_scan: Optional[datetime] = None

        # Ensure directory exists
        self._persistence_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing registry
        self._load_from_disk()

    @property
    def last_scan_time(self) -> Optional[datetime]:
        """Time of the last scan."""
        return self._last_scan

    def refresh(
        self,
        directories: Optional[List[Path]] = None,
        parallel: bool = True,
    ) -> List[ElectronApp]:
        """
        Rescan directories and update the registry.

        Args:
            directories: Directories to scan (uses defaults if None)
            parallel: Whether to scan in parallel

        Returns:
            List of newly discovered apps
        """
        print("Scanning for Electron apps...")
        apps = scan_all_directories(directories, parallel)

        new_apps = []
        for app in apps:
            if app.name not in self._apps:
                new_apps.append(app)
            self._apps[app.name] = app

        self._last_scan = datetime.now()
        self._persist_to_disk()

        print(f"Found {len(apps)} Electron app(s), {len(new_apps)} new")
        return new_apps

    def get_by_name(self, name: str) -> Optional[ElectronApp]:
        """Get an app by name."""
        return self._apps.get(name)

    def get_by_bundle_id(self, bundle_id: str) -> Optional[ElectronApp]:
        """Get an app by bundle identifier."""
        for app in self._apps.values():
            if app.bundle_id == bundle_id:
                return app
        return None

    def search(self, query: str) -> List[ElectronApp]:
        """
        Search for apps by name (case-insensitive partial match).

        Args:
            query: Search query

        Returns:
            List of matching apps
        """
        query_lower = query.lower()
        return [
            app for app in self._apps.values()
            if query_lower in app.name.lower()
        ]

    def all_apps(self) -> List[ElectronApp]:
        """Get all registered apps."""
        return list(self._apps.values())

    def __iter__(self) -> Iterator[ElectronApp]:
        """Iterate over all apps."""
        return iter(self._apps.values())

    def __len__(self) -> int:
        """Number of registered apps."""
        return len(self._apps)

    def __contains__(self, name: str) -> bool:
        """Check if an app is registered."""
        return name in self._apps

    def remove(self, name: str) -> Optional[ElectronApp]:
        """Remove an app from the registry."""
        if app := self._apps.pop(name, None):
            self._persist_to_disk()
            return app
        return None

    def clear(self) -> None:
        """Clear all apps from the registry."""
        self._apps.clear()
        self._persist_to_disk()

    def _persist_to_disk(self) -> None:
        """Save registry to disk."""
        data = {
            "version": 1,
            "last_scan": self._last_scan.isoformat() if self._last_scan else None,
            "apps": [app.to_dict() for app in self._apps.values()],
        }

        temp_path = self._persistence_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._persistence_path)
        except IOError as e:
            print(f"Warning: Could not persist app registry: {e}")
            if temp_path.exists():
                temp_path.unlink()

    def _load_from_disk(self) -> None:
        """Load registry from disk."""
        if not self._persistence_path.exists():
            return

        try:
            with open(self._persistence_path, "r") as f:
                data = json.load(f)

            if data.get("last_scan"):
                self._last_scan = datetime.fromisoformat(data["last_scan"])

            for app_dict in data.get("apps", []):
                try:
                    app = ElectronApp.from_dict(app_dict)
                    self._apps[app.name] = app
                except Exception as e:
                    print(f"Warning: Could not load app: {e}")

        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load app registry: {e}")

    def print_table(self) -> None:
        """Print a formatted table of all apps."""
        if not self._apps:
            print("No Electron apps registered. Run refresh() to scan.")
            return

        # Calculate column widths
        name_width = max(len(app.name) for app in self._apps.values())
        name_width = max(name_width, 4)  # Minimum "Name"

        print(f"\n{'Name':<{name_width}}  {'Chrome':<20}  {'Electron':<12}  Path")
        print("-" * (name_width + 60))

        for app in sorted(self._apps.values(), key=lambda a: a.name.lower()):
            chrome = app.chrome_version or "?"
            electron = app.electron_version or "?"
            print(f"{app.name:<{name_width}}  {chrome:<20}  {electron:<12}  {app.app_bundle}")


# Module-level singleton
_app_registry: Optional[AppRegistry] = None


def get_app_registry() -> AppRegistry:
    """Get or create the global app registry."""
    global _app_registry
    if _app_registry is None:
        _app_registry = AppRegistry()
    return _app_registry


def reset_app_registry() -> None:
    """Reset the global app registry singleton."""
    global _app_registry
    _app_registry = None


# ============================================================================
# CLI for standalone usage
# ============================================================================

def main():
    """CLI entry point for app scanning."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scan for Electron applications"
    )
    parser.add_argument(
        "--refresh", "-r",
        action="store_true",
        help="Rescan directories for apps"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all registered apps"
    )
    parser.add_argument(
        "--search", "-s",
        type=str,
        help="Search for apps by name"
    )
    parser.add_argument(
        "--info", "-i",
        type=str,
        help="Show detailed info for an app"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--directory", "-d",
        type=str,
        action="append",
        help="Additional directory to scan (can be used multiple times)"
    )

    args = parser.parse_args()

    registry = get_app_registry()

    # Handle refresh
    if args.refresh or (not registry.all_apps() and not args.search and not args.info):
        extra_dirs = [Path(d) for d in args.directory] if args.directory else None
        registry.refresh(directories=extra_dirs)

    # Handle search
    if args.search:
        results = registry.search(args.search)
        if args.json:
            print(json.dumps([app.to_dict() for app in results], indent=2))
        elif results:
            for app in results:
                print(f"{app.name}: Chrome {app.chrome_version or '?'} - {app.app_bundle}")
        else:
            print(f"No apps matching '{args.search}'")
        return

    # Handle info
    if args.info:
        app = registry.get_by_name(args.info)
        if not app:
            # Try partial match
            matches = registry.search(args.info)
            if len(matches) == 1:
                app = matches[0]

        if app:
            if args.json:
                print(json.dumps(app.to_dict(), indent=2))
            else:
                print(f"\nName:            {app.name}")
                print(f"Bundle ID:       {app.bundle_id or 'N/A'}")
                print(f"Version:         {app.version or 'N/A'}")
                print(f"Chrome Version:  {app.chrome_version or 'N/A'}")
                print(f"Electron:        {app.electron_version or 'N/A'}")
                print(f"App Bundle:      {app.app_bundle}")
                print(f"Binary:          {app.binary}")
                print(f"Framework:       {app.electron_framework}")
        else:
            print(f"App not found: {args.info}")
        return

    # Default: list all apps
    if args.json:
        print(json.dumps([app.to_dict() for app in registry.all_apps()], indent=2))
    else:
        registry.print_table()


if __name__ == "__main__":
    main()
