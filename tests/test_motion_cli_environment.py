"""Independent CLI shells retain the launcher's pinned native tool environment."""
from pathlib import Path
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('motion_cli_test', ROOT / 'Haike_video/scripts/motion_replay_production.py')
cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)


class MotionCliEnvironmentTests(unittest.TestCase):
    def test_legacy_mac_source_without_native_installer_keeps_existing_tools(self):
        with patch.object(cli.sys, 'platform', 'darwin'), patch.dict(os.environ, {'PATH': 'legacy-tools'}), \
             patch.object(cli.Path, 'is_file', return_value=False), \
             patch.object(cli.importlib.util, 'module_from_spec') as loader:
            cli.prepare_platform_environment()
            loader.assert_not_called()
            self.assertEqual(os.environ['PATH'], 'legacy-tools')

    def test_windows_preserves_its_existing_execution_environment(self):
        with patch.object(cli.sys, 'platform', 'win32'), patch.dict(os.environ, {'PATH': 'existing-tools'}), \
             patch.object(cli.importlib.util, 'module_from_spec') as loader:
            cli.prepare_platform_environment()
            loader.assert_not_called()
            self.assertEqual(os.environ['PATH'], 'existing-tools')

    def test_fresh_mac_shell_loads_the_fixed_installer_environment(self):
        deployment = SimpleNamespace(architecture=Mock(return_value='arm64'),
            environment=Mock(return_value={'PATH': '/fixture/native/bin', 'HAIKE_NODE_EXECUTABLE': '/fixture/native/bin/node'}))
        module_spec = SimpleNamespace(loader=Mock())
        with patch.object(cli.sys, 'platform', 'darwin'), patch.dict(os.environ, {'PATH': 'system-only'}), \
             patch.object(cli.Path, 'is_file', return_value=True), \
             patch.object(cli.importlib.util, 'spec_from_file_location', return_value=module_spec) as locate, \
             patch.object(cli.importlib.util, 'module_from_spec', return_value=deployment):
            cli.prepare_platform_environment()
            locate.assert_called_once_with('haike_motion_cli_mac', ROOT / 'scripts/mac-deploy.py')
            deployment.environment.assert_called_once_with('arm64')
            module_spec.loader.exec_module.assert_called_once_with(deployment)
            self.assertEqual(os.environ['PATH'], '/fixture/native/bin')
            self.assertEqual(os.environ['HAIKE_NODE_EXECUTABLE'], '/fixture/native/bin/node')


if __name__ == '__main__':
    unittest.main()
