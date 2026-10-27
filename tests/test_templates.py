"""Render the real templates in temporary directories without starting services."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

try:
    from supervisor.options import ServerOptions
except ImportError:
    ServerOptions = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == "nt", "Requires Linux bash and envsubst")
class TemplateTests(unittest.TestCase):
    """Verify substitution, validation, defaults and secret escaping."""

    def render(self, directory, overrides=None):
        """Run only the entrypoint's rendering functions, never its main routine."""
        environment = os.environ.copy()
        environment.update({
            "BAREOS_DIR_HOSTNAME": "test-dir",
            "BAREOS_DIR_PASSWORD": 'password"with\\symbols$HOME',
            "BAREOS_STORAGE_NAME": "Test Tape",
        })
        environment.update(overrides or {})
        command = [
            "bash", "-c",
            'source "$1"; set_defaults; validate_settings; render_configuration "$2" "$3" "$4"',
            "test",
            str(ROOT / "entrypoint.sh"),
            str(ROOT / "templates"),
            str(directory / "config"),
            str(directory / "runtime"),
        ]
        return subprocess.run(command, env=environment, capture_output=True, text=True)

    def test_defaults_and_password_escaping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self.render(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            director = (root / "config/director/bareos-dir.conf").read_text()
            self.assertIn('Password = "password\\"with\\\\symbols$HOME"', director)
            device = (root / "config/device/device-lto.conf").read_text()
            self.assertIn('Archive Device = "/dev/nst0"', device)
            self.assertIn('Name = "HP-TapeDrive0"', device)
            self.assertNotIn("${", device)
            self.assertEqual((root / "runtime/hooks.json").stat().st_mode & 0o777, 0o600)

    def test_custom_ports_device_and_fixed_hooks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self.render(root, {
                "TAPE_DEVICE": "/dev/nst1",
                "BAREOS_STORAGE_DEVICE_NAME": "Other Tape",
                "BAREOS_STORAGE_PORT": "9107",
                "TAPE_WEBHOOK_PORT": "9099",
                "TAPE_WEBHOOK_ENABLED": "yes",
                "TAPE_WEBHOOK_TOKEN": "x" * 32,
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            device = (root / "config/device/device-lto.conf").read_text()
            self.assertIn('Archive Device = "/dev/nst1"', device)
            self.assertIn('Name = "Other Tape"', device)
            self.assertIn('SD Port = 9107', (root / "config/storage/bareos-sd.conf").read_text())
            hooks = json.loads((root / "runtime/hooks.json").read_text())
            for hook in hooks:
                self.assertEqual(hook["trigger-rule"]["match"]["value"], "x" * 32)
                self.assertEqual(hook["pass-arguments-to-command"], [
                    {"source": "string", "name": hook["id"]},
                ])
                self.assertNotIn("pass-environment-to-command", hook)
            self.assertEqual(hooks[0]["http-methods"], ["GET"])
            self.assertEqual(hooks[1]["http-methods"], ["POST"])

    def test_invalid_values_fail_before_writing_configuration(self):
        invalid_settings = [
            {"TAPE_WEBHOOK_ENABLED": "true"},
            {"TAPE_DEVICE": "/dev/nst0;erase"},
            {"TAPE_COMMAND_TIMEOUT": "0"},
            {"BAREOS_STORAGE_PORT": "65536"},
            {"BAREOS_DIR_PASSWORD": "secret\nnew directive"},
            {"BAREOS_ALWAYS_OPEN": "perhaps"},
        ]
        for overrides in invalid_settings:
            with self.subTest(overrides=overrides), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = self.render(root, overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "config").exists())
                self.assertNotIn("secret", result.stderr)

    @unittest.skipIf(ServerOptions is None, "Requires Supervisor for configuration parsing")
    def test_static_supervisor_uses_runtime_port_and_enable_flag(self):
        for enabled in ("true", "false"):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
                "TAPE_WEBHOOK_ENABLED": enabled,
                "TAPE_WEBHOOK_PORT": "9099",
                "TAPE_WEBHOOK_LISTEN_ADDRESS": "127.0.0.1",
            }):
                # Only relocate the runtime pid path; do not create system directories.
                contents = (ROOT / "supervisord.conf").read_text()
                contents = contents.replace("/run/tape-webhook/supervisord.pid", f"{temporary}/supervisord.pid")
                config_path = Path(temporary) / "supervisord.conf"
                config_path.write_text(contents)
                options = ServerOptions()
                options.realize(["-c", str(config_path)])
                groups = {group.name: group for group in options.process_group_configs}
                webhook = groups["webhook"].process_configs[0]
                self.assertEqual(webhook.autostart, enabled == "true")
                self.assertIn("-ip 127.0.0.1 -port 9099", webhook.command)


if __name__ == "__main__":
    unittest.main()
