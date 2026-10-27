# Bareos SD tape container

Runs one Bareos Storage Daemon tape device with optional HTTP eject/status hooks
provided by [adnanh/webhook](https://github.com/adnanh/webhook). Supervisor owns
both processes, forwards container shutdown to their process groups, and restarts
an unexpectedly exited process. The image retains Debian Bookworm and the existing
Bareos package source. It does not implement a custom HTTP server.

## Configure and run

Copy `env.example` to ignored `env`, set the Director password and resource names,
and match the existing tape Device resource name before deploying. To enable the
hooks, set `TAPE_WEBHOOK_ENABLED=true` and a dedicated `TAPE_WEBHOOK_TOKEN` of at
least 32 letters, digits, underscores or hyphens. For example, `openssl rand -hex 32`
generates a suitable token. Do not commit the resulting env file.

```sh
docker build -t bareos-sd-tape:local .

# Set these shell variables to the intended host/container device and host ports.
HOST_TAPE_DEVICE=/dev/nst0
TAPE_DEVICE=/dev/nst0
SD_HOST_PORT=9103
WEBHOOK_HOST_PORT=9080

docker run -d --name bareos-sd-tape --restart unless-stopped \
  --env-file env --device "${HOST_TAPE_DEVICE}:${TAPE_DEVICE}" \
  -p "${SD_HOST_PORT}:9103" -p "${WEBHOOK_HOST_PORT}:9080" \
  -v bareos-tape-spool:/var/spool/bareos \
  bareos-sd-tape:local
```

Set `TAPE_DEVICE` inside `env` to the same container path as the device mapping.
The example maps default internal ports; if you change `BAREOS_STORAGE_PORT` or
`TAPE_WEBHOOK_PORT`, update the right-hand sides of `-p` too. The Dockerfile deliberately has no numeric `EXPOSE` declarations: ports are
runtime settings, and `-p` or Compose publishes them explicitly. For container-to-container use, a shared Docker
network can reach the configured webhook port without publishing it to the host.
Bind published ports only on the intended internal interface. The HTTP token is
not encryption; use a trusted network or an HTTPS reverse proxy.

## HTTP endpoints

Every request needs `X-Tape-Token: <configured token>`. There are exactly two hooks:

| Method | Path | Fixed operation |
| --- | --- | --- |
| GET | `/hooks/status` | `mt -f "$TAPE_DEVICE" status` |
| POST | `/hooks/eject` | `mt -f "$TAPE_DEVICE" offline` |

Requests cannot select a device, command, or arguments. Both operations share a
nonblocking lock: overlapping requests fail instead of queuing a delayed eject.
The hook waits for command completion and returns JSON with `ok`, output/error,
and command exit code when available. A command failure returns HTTP 500 with
diagnostics; wrong tokens return 403 and disallowed methods are rejected.
`mt status` can fail when the drive is open exclusively or has no tape; that is
reported as command failure, not fabricated ready status. Its output remains
the device/driver's native text.

```sh
TAPE_WEBHOOK_URL=http://tape-container:9080
# TAPE_WEBHOOK_TOKEN should already be set securely in your shell.
curl --fail-with-body -H "X-Tape-Token: $TAPE_WEBHOOK_TOKEN" \
  "$TAPE_WEBHOOK_URL/hooks/status"

# First unmount through Bareos and confirm success, then explicitly eject:
curl --fail-with-body -X POST -H "X-Tape-Token: $TAPE_WEBHOOK_TOKEN" \
  "$TAPE_WEBHOOK_URL/hooks/eject"
```

The helper checks `fuser` before eject and refuses if the device has open handles
or the check fails. This is a secondary guard, not a substitute for Bareos
unmount: it cannot coordinate other containers/hosts or eliminate races with a
new opener. Keep tape control in one container and prevent independent tape
commands while swapping media. After inserting the requested tape and allowing
the drive to initialize, mount through Bareos again. A completed `offline` command
means the driver accepted/completed it; physical behavior remains drive-specific.
A timeout is an unknown outcome: inspect status before retrying, never retry
eject automatically. No Docker socket or SSH access is needed.

## Environment variables

| Setting | Default | Purpose |
| --- | --- | --- |
| `BAREOS_DIR_HOSTNAME` | Required | Director resource name |
| `BAREOS_DIR_PASSWORD` | Required | Director authentication password |
| `BAREOS_STORAGE_NAME` | Required | Storage daemon resource name |
| `BAREOS_STORAGE_PORT` | `9103` | SD listen port |
| `BAREOS_STORAGE_DEVICE_NAME` | `HP-TapeDrive0` | Single Device resource name |
| `BAREOS_MEDIA_TYPE` | `LTO-5` | Match the Director storage Media Type |
| `TAPE_DEVICE` | `/dev/nst0` | Container tape character-device path |
| `TAPE_WEBHOOK_ENABLED` | `false` | Start the HTTP listener |
| `TAPE_WEBHOOK_TOKEN` | Empty | Required when hooks are enabled |
| `TAPE_WEBHOOK_LISTEN_ADDRESS` | `0.0.0.0` | Listener IP address |
| `TAPE_WEBHOOK_PORT` | `9080` | Listener port |
| `TAPE_COMMAND_TIMEOUT` | `180` | Seconds before command timeout, 1–3600 |
| `BAREOS_AUTOMATIC_MOUNT` | `yes` | Device Automatic Mount |
| `BAREOS_ALWAYS_OPEN` | `yes` | Device Always Open |
| `BAREOS_OFFLINE_ON_UNMOUNT` | `yes` | Device Offline On Unmount |
| `BAREOS_MAXIMUM_CHANGER_WAIT` | `600` | Seconds |
| `BAREOS_MAXIMUM_REWIND_WAIT` | `600` | Seconds |
| `BAREOS_MAXIMUM_OPEN_WAIT` | `600` | Seconds |
| `BAREOS_MAXIMUM_CONCURRENT_JOBS` | `1` | Concurrent jobs for this device |
| `BAREOS_SPOOL_DIRECTORY` | `/var/spool/bareos` | Spool path; mount capacity here |
| `BAREOS_MAXIMUM_SPOOL_SIZE` | `60G` | Spool size limit |
| `TAPE_SET_BLOCK_SIZE` | `yes` | Preserve startup `mt defblksize` behavior |
| `TAPE_BLOCK_SIZE` | `0` | Default block size; zero means variable |

Startup applies defaults in `entrypoint.sh`, validates settings, renders the
readable files in `templates/` using an explicit `envsubst` variable list, and runs `bareos-sd -t` before the optional block-size
command. Setting `TAPE_SET_BLOCK_SIZE=no` avoids that startup device operation.
Supervisor reads the static `supervisord.conf` and its built-in environment
substitutions. Runtime files under `/run/tape-webhook` and generated configuration
are private. The Director password is escaped before substitution; other
substituted values are checked to prevent invalid configuration syntax.
Do not enable webhook verbose logging with production credentials.

`BAREOS_DIR_ADDRESS` and `BAREOS_STORAGE_DEVICE_NO` were previously required but
unused; they are no longer required and have no effect. This image configures
one drive, not a drive count. `BAREOS_STORAGE_DEVICE_NAME` was also previously
ignored: it is now honored. If an old deployment sets it to a different name,
correct it to match the existing tape Device before updating the container.

## Verification and project map

```sh
python3 -m unittest discover -s tests -v
bash -n entrypoint.sh
docker build -t bareos-sd-tape:local .
```

Unit tests use simulated commands; they do not contact a Director or tape.
Set `WEBHOOK_TEST_BINARY` to a locally installed webhook executable to also run
the localhost HTTP integration test, which substitutes a harmless fake command.
Before production deployment, verify generated config syntax and both HTTP hooks
on a non-production drive. Do not test eject on active backup media.

- `Dockerfile`: existing Bareos packages plus webhook, Supervisor and helpers.
- `entrypoint.sh`: configuration validation, optional block-size setup, startup.
- `templates/`: editable Bareos resources and adnanh/webhook hook definitions.
- `supervisord.conf`: static process management, with environment-based ports.
- `tape-control.py`: separate `get_tape_status()` and `eject_tape()` paths, shared
  command/result helpers, locking and one JSON serialization step.
- `env.example`: settings without real credentials.
- `tests/`: isolated configuration and command tests.

Licensed under MIT; see `LICENSE`.
