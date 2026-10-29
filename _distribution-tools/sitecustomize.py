"""Preload the bundle's complete VC runtime before native Python extensions."""
import ctypes
import os
from pathlib import Path

_bundle_handles = []
if os.name == 'nt':
    _bundle_dll_dir = Path(__file__).resolve().parents[2] / 'msvc'
    _bundle_dll_cookie = os.add_dll_directory(str(_bundle_dll_dir))
    for _bundle_dll_name in ('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll'):
        _bundle_handles.append(ctypes.WinDLL(str(_bundle_dll_dir / _bundle_dll_name)))
