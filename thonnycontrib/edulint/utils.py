# Copied from https://github.com/GiraffeReversed/edulint-web/blob/main/utils.py

import os
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import functools
import sys

from packaging import version as packaging_version


@dataclass
class Version(packaging_version.Version):
    def __init__(self, version: str) -> None:
        super().__init__(version)

    def is_not_full_release(self) -> bool:
        return not(self.is_prerelease or self.is_postrelease or self.is_devrelease)

    def name(self) -> str:
        return str(self).replace(".", "_")

    def dir(self, prefix: str) -> str:
        return f"{prefix}_{self.name()}"

    def __str__(self) -> str:
        return super().__str__()

    def __repr__(self) -> str:
        return super().__repr__()

    @staticmethod
    def parse(version_raw: str) -> Optional["Version"]:
        try:
            return Version(version_raw)
        except packaging_version.InvalidVersion:
            return None


@functools.lru_cache
def get_available_versions(versions_raw: List[str]) -> List[Version]:
    return [Version(v) for v in versions_raw]

# Context manager for temporary inclusion of one path in sys.path
# https://stackoverflow.com/a/39855753
class add_path():
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        sys.path.insert(0, self.path)

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            sys.path.remove(self.path)
        except ValueError:
            pass

def get_pylint_plugins_dir() -> str:
    # TODO: some fallback?
    return [path for path in sys.path if os.path.join("thonny", "plugins") in path.lower()][0]
