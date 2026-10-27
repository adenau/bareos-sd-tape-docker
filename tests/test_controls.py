# File Name: test_controls.py
# Purpose: Validate tape container configuration and restricted commands offline.
# Overview: Uses temporary settings and mocked subprocesses, never real tape I/O.
"""Standard-library regression tests for the tape container."""

import configparser
from contextlib import redirect_stdout
import io
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


spec = importlib.util.spec_from_file_location("tape_control", ROOT / "tape-control.py")
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def environment(**overrides):
    """Return fictitious required resource values plus test overrides."""
    return {"BAREOS_DIR_HOSTNAME": "test-dir", "BAREOS_DIR_PASSWORD": 'test"secret\\value',
            "BAREOS_STORAGE_NAME": "Test Tape", **overrides}


class CommandTests(unittest.TestCase):
    """Verify precise commands, busy detection, failure handling and no retries."""

    def runner(self, results):
        """Build a command recorder using a sequence of fake outcomes."""
        self.calls = []

        def run(command, **kwargs):
            self.calls.append((command, kwargs))
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return run

    def test_eject_checks_busy_then_offlines_configured_device(self):
        run = self.runner([SimpleNamespace(returncode=1, stderr=""),
                           SimpleNamespace(returncode=0, stdout="", stderr="")])
        result = control.execute("eject", "/dev/nst1", 42, run)
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[0][0], ["/usr/bin/fuser", "/dev/nst1"])
        self.assertEqual(self.calls[1][0], ["/usr/bin/mt", "-f", "/dev/nst1", "offline"])
        self.assertEqual(self.calls[1][1]["timeout"], 42)

    def test_busy_or_uncertain_device_never_ejects(self):
        for code, stderr in [(0, ""), (1, "inspection failed"), (2, "")]:
            run = self.runner([SimpleNamespace(returncode=code, stderr=stderr)])
            self.assertFalse(control.execute("eject", "/dev/nst0", 10, run)["ok"])
            self.assertEqual(len(self.calls), 1)

    def test_status_is_read_only_and_returns_failure_output(self):
        run = self.runner([SimpleNamespace(returncode=1, stdout="", stderr="No medium found")])
        result = control.execute("status", "/dev/nst0", 10, run)
        self.assertEqual(self.calls[0][0][-1], "status")
        self.assertFalse(result["ok"])
        self.assertIn("No medium", result["error"])

    def test_timeout_is_unknown_without_retry(self):
        run = self.runner([subprocess.TimeoutExpired("mt", 10)])
        result = control.execute("status", "/dev/nst0", 10, run)
        self.assertIn("outcome unknown", result["error"])
        self.assertEqual(len(self.calls), 1)

    def test_arbitrary_commands_are_rejected(self):
        run = self.runner([])
        self.assertFalse(control.execute("erase", "/dev/nst0", 10, run)["ok"])
        self.assertEqual(self.calls, [])

    @unittest.skipIf(os.name == "nt", "Linux flock semantics")
    def test_busy_hook_lock_prevents_any_device_command(self):
        """The real helper lock excludes overlapping requests without tape I/O."""
        import fcntl
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "device.lock"
            with path.open("a") as owner:
                fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with path.open("a") as contender:
                    output = io.StringIO()
                    with patch("builtins.open", return_value=contender), \
                         patch.dict(os.environ, {"TAPE_DEVICE": "/dev/null", "TAPE_COMMAND_TIMEOUT": "10"}), \
                         patch.object(sys, "argv", ["tape-control.py", "eject"]), \
                         patch.object(control, "execute") as execute, redirect_stdout(output):
                        self.assertEqual(control.main(), 1)
                    execute.assert_not_called()
                    self.assertIn("in progress", json.loads(output.getvalue())["error"])


if __name__ == "__main__":
    unittest.main()
