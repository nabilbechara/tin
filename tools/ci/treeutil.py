"""Helpers for the checks that build a throwaway Tin tree."""
from pathlib import Path
import shutil


def copy_lib(root, lib):
    """Copy the runtime, the standard library and the packages of the tree at root into one lib/ directory."""
    root, lib = Path(root), Path(lib)
    lib.mkdir(parents=True, exist_ok=True)
    shutil.copytree(root / 'toolchain/runtime', lib / 'runtime')
    for part in ('toolchain/std', 'packages'):
        for child in sorted((root / part).iterdir()):
            if child.is_dir():
                shutil.copytree(child, lib / child.name)


def copy_tree(root, dest):
    """Copy the runtime, the standard library and the packages of the tree at root into dest, keeping the tree layout."""
    root, dest = Path(root), Path(dest)
    shutil.copytree(root / 'toolchain/runtime', dest / 'toolchain/runtime')
    shutil.copytree(root / 'toolchain/std', dest / 'toolchain/std')
    shutil.copytree(root / 'packages', dest / 'packages')
