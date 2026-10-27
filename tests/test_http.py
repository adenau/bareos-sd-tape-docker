# File Name: test_http.py
# Purpose: Exercise real webhook HTTP routing against a fake command only.
# Overview: Optional localhost integration test uses WEBHOOK_TEST_BINARY and
# temporary hook files to validate methods, authentication and response codes.
"""No tape command is ever invoked by these HTTP tests."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))



@unittest.skipUnless(os.environ.get("WEBHOOK_TEST_BINARY"), "Set WEBHOOK_TEST_BINARY for localhost integration")
class HttpTests(unittest.TestCase):
    """Use the real webhook server with a harmless simulated command."""

    def test_authentication_methods_fixed_arguments_and_command_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            helper = root / "fake.py"
            helper.write_text('import json,sys\nprint(json.dumps({"action":sys.argv[1]}))\nsys.exit(7 if sys.argv[1]=="status" else 0)\n')
            template = Path(__file__).resolve().parents[1] / "templates" / "hooks.json.template"
            hook_text = template.read_text().replace("${TAPE_WEBHOOK_TOKEN}", "x" * 32)
            hooks = json.loads(hook_text)
            for hook in hooks:
                hook["execute-command"] = sys.executable
                hook["pass-arguments-to-command"].insert(0, {"source": "string", "name": str(helper)})
            hook_file = root / "hooks.json"
            hook_file.write_text(json.dumps(hooks))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            process = subprocess.Popen([os.environ["WEBHOOK_TEST_BINARY"], "-ip", "127.0.0.1",
                                        "-port", str(port), "-hooks", str(hook_file)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def request(action, method, token="x" * 32, body=None):
                """Call a localhost-only hook and return status and body."""
                req = Request(f"http://127.0.0.1:{port}/hooks/{action}", method=method, data=body,
                              headers={"X-Tape-Token": token, "Content-Type": "application/json"})
                try:
                    with urlopen(req, timeout=2) as response:
                        return response.status, response.read()
                except HTTPError as error:
                    with error:
                        return error.code, error.read()

            try:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        code, _ = request("status", "GET", token="wrong")
                        break
                    except URLError:
                        if time.monotonic() >= deadline or process.poll() is not None:
                            self.fail("Local webhook server did not start")
                        time.sleep(0.05)
                self.assertEqual(code, 403)
                self.assertEqual(request("eject", "GET")[0], 405)
                self.assertEqual(request("status", "POST", body=b'{}')[0], 405)
                code, body = request("eject", "POST", body=b'{"action":"erase","device":"/dev/other"}')
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(body)["action"], "eject")
                code, body = request("status", "GET")
                self.assertEqual(code, 500)
                self.assertEqual(json.loads(body)["action"], "status")
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
