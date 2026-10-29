from pathlib import Path
import os
import shlex
import tempfile
import unittest
from unittest.mock import patch

import backend


class LauncherStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vader5 status ')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.driver = self.home / '.local/share/vader5-driver/sdl'
        self.driver.mkdir(parents=True)
        self.launcher = self.home / '.local/bin/steam'
        self.launcher.parent.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(backend, 'HOME', self.home).start()
        patch.object(backend, 'WINDOWS', False).start()
        patch.dict(os.environ, {'VADER5_DRIVER_DIR': str(self.driver)}).start()

    def install(self):
        for name in ('libSDL3-64.so.0', 'sdl3_shim64.so', 'steam-sdl-loader.so'):
            (self.driver / name).write_bytes(b'fixture')
        private = self.driver / 'steam64'
        private.mkdir()
        (private / 'libSDL3.so.0').symlink_to('../libSDL3-64.so.0')
        (private / 'sdl3_shim.so').symlink_to('../sdl3_shim64.so')
        self.launcher.write_text('\n'.join((
            '#!/usr/bin/env bash',
            'export VADER5_STEAM_ROOT=' + shlex.quote(str(self.home / 'Steam')),
            'export VADER5_PRIVATE_SDL=' + shlex.quote(str(private / 'libSDL3.so.0')),
            'loader=' + shlex.quote(str(self.driver / 'steam-sdl-loader.so')),
            'export LD_PRELOAD="${LD_PRELOAD:+$LD_PRELOAD:}$loader"',
            'exec /usr/bin/steam "$@"')) + '\n')
        self.launcher.chmod(0o755)

    def test_launcher_works_without_legacy_patch_receipts(self):
        self.install()
        self.assertTrue(backend.patch_status())

    def test_wrong_private_library_is_not_reported_as_patched(self):
        self.install()
        link = self.driver / 'steam64/libSDL3.so.0'
        link.unlink()
        link.symlink_to('../sdl3_shim64.so')
        self.assertFalse(backend.patch_status())

    def test_unrelated_launcher_is_not_reported_as_patched(self):
        self.install()
        self.launcher.write_text('#!/bin/sh\nexec /usr/bin/steam "$@"\n')
        self.assertFalse(backend.patch_status())

    def test_no_installation_is_unknown(self):
        self.assertIsNone(backend.patch_status())
