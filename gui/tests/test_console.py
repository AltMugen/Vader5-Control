import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend


class ConsoleTests(unittest.TestCase):
    def test_desktop_path_without_local_bin_finds_installed_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            cli = home / '.local/bin/vader5'
            cli.parent.mkdir(parents=True)
            cli.write_text('#!/bin/sh\nexit 0\n')
            cli.chmod(0o755)
            with patch.object(backend, 'HOME', home), \
                 patch.object(backend, 'WINDOWS', False), \
                 patch.dict(os.environ, {'PATH': '/usr/bin:/bin'}), \
                 patch.object(backend, 'run') as run:
                backend.console('update')
            self.assertEqual(run.call_args.args[0], [str(cli), 'update'])

    def test_explicit_path_command_keeps_precedence(self):
        with patch.object(backend, 'WINDOWS', False), \
             patch.object(backend.shutil, 'which', return_value='/opt/bin/vader5'), \
             patch.object(backend, 'run') as run:
            backend.console('native')
        self.assertEqual(run.call_args.args[0], ['/opt/bin/vader5', 'native'])
