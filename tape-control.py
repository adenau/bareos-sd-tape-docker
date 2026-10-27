#!/usr/bin/env python3
"""Run fixed tape commands and return a JSON result to adnanh/webhook."""

import json
import os
from pathlib import Path
import stat
import subprocess
import sys

MAX_OUTPUT_LENGTH = 8192
DEVICE_LOCK = "/run/tape-webhook/device.lock"


def failure(message):
    """Build a consistent failure result without serializing it yet."""
    return {
        "ok": False,
        "error": message,
    }


def run_tape_command(action, device, command, timeout, run):
    """Execute one mt command and build its result dictionary."""
    completed = run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    succeeded = completed.returncode == 0
    message = "Tape command failed."
    if succeeded:
        if action == "eject":
            message = "Eject command completed."
        else:
            message = "Tape status retrieved."

    return {
        "ok": succeeded,
        "action": action,
        "device": device,
        "exit_code": completed.returncode,
        "output": completed.stdout[-MAX_OUTPUT_LENGTH:],
        "error": completed.stderr[-MAX_OUTPUT_LENGTH:],
        "message": message,
    }


def get_tape_status(device, timeout, run):
    """Read the drive's status without moving or ejecting the tape."""
    command = ["/usr/bin/mt", "-f", device, "status"]
    return run_tape_command("status", device, command, timeout, run)


def eject_tape(device, timeout, run):
    """Refuse an open device, otherwise issue the tape offline command."""
    busy_check = run(
        ["/usr/bin/fuser", device],
        capture_output=True,
        text=True,
        timeout=10,
    )

    if busy_check.returncode == 0:
        return failure("Device is open. Unmount it in Bareos before ejecting.")

    if busy_check.returncode != 1 or busy_check.stderr.strip():
        return failure("Could not establish whether the device is in use.")

    command = ["/usr/bin/mt", "-f", device, "offline"]
    return run_tape_command("eject", device, command, timeout, run)


def execute(action, device, timeout, run=subprocess.run):
    """Dispatch an allowed action and translate command failures into results."""
    try:
        if action == "status":
            return get_tape_status(device, timeout, run)

        if action == "eject":
            return eject_tape(device, timeout, run)

        return failure("Unsupported tape action.")
    except subprocess.TimeoutExpired:
        return failure("Tape command timed out; outcome unknown. Check the drive before retrying.")
    except OSError:
        return failure("Unable to execute the tape command.")


def validate_device(device):
    """Require an absolute character-device path under /dev."""
    if not device.startswith("/dev/") or ".." in Path(device).parts:
        raise ValueError("TAPE_DEVICE must be a path under /dev.")

    device_info = os.stat(device)
    if not stat.S_ISCHR(device_info.st_mode):
        raise ValueError("TAPE_DEVICE must be a character device.")


def execute_with_lock(action, device, timeout):
    """Prevent simultaneous webhook operations on the configured tape drive."""
    import fcntl

    with open(DEVICE_LOCK, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return failure("Another tape webhook operation is in progress.")

        return execute(action, device, timeout)


def handle_request(arguments, environment):
    """Validate inputs and return one result dictionary for the CLI request."""
    if len(arguments) != 1 or arguments[0] not in {"status", "eject"}:
        return failure("Expected one action: status or eject.")

    action = arguments[0]
    device = environment.get("TAPE_DEVICE", "/dev/nst0")

    try:
        timeout = int(environment.get("TAPE_COMMAND_TIMEOUT", "180"))
    except ValueError:
        return failure("TAPE_COMMAND_TIMEOUT must be an integer.")

    if not 1 <= timeout <= 3600:
        return failure("TAPE_COMMAND_TIMEOUT must be between 1 and 3600 seconds.")

    try:
        validate_device(device)
        return execute_with_lock(action, device, timeout)
    except ValueError as error:
        return failure(str(error))
    except OSError:
        return failure("The tape device or runtime lock file is unavailable.")


def main():
    """Serialize the completed result once, then report success to webhook."""
    result = handle_request(sys.argv[1:], os.environ)
    print(json.dumps(result), flush=True)

    if result["ok"]:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
