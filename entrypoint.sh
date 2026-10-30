#!/bin/bash
# Render the configuration templates, validate Bareos, then start Supervisor.
set -euo pipefail

set_defaults() {
  export BAREOS_STORAGE_PORT="${BAREOS_STORAGE_PORT:-9103}"
  export BAREOS_DEBUG_LEVEL="${BAREOS_DEBUG_LEVEL:-0}"
  export BAREOS_STORAGE_DEVICE_NAME="${BAREOS_STORAGE_DEVICE_NAME:-HP-TapeDrive0}"
  export BAREOS_MEDIA_TYPE="${BAREOS_MEDIA_TYPE:-LTO-5}"
  export TAPE_DEVICE="${TAPE_DEVICE:-/dev/nst0}"
  export BAREOS_SPOOL_DIRECTORY="${BAREOS_SPOOL_DIRECTORY:-/var/spool/bareos}"
  export BAREOS_MAXIMUM_SPOOL_SIZE="${BAREOS_MAXIMUM_SPOOL_SIZE:-60G}"
  export BAREOS_MAXIMUM_CHANGER_WAIT="${BAREOS_MAXIMUM_CHANGER_WAIT:-600}"
  export BAREOS_MAXIMUM_REWIND_WAIT="${BAREOS_MAXIMUM_REWIND_WAIT:-600}"
  export BAREOS_MAXIMUM_OPEN_WAIT="${BAREOS_MAXIMUM_OPEN_WAIT:-600}"
  export BAREOS_MAXIMUM_CONCURRENT_JOBS="${BAREOS_MAXIMUM_CONCURRENT_JOBS:-1}"
  export BAREOS_AUTOMATIC_MOUNT="${BAREOS_AUTOMATIC_MOUNT:-yes}"
  export BAREOS_ALWAYS_OPEN="${BAREOS_ALWAYS_OPEN:-yes}"
  export BAREOS_OFFLINE_ON_UNMOUNT="${BAREOS_OFFLINE_ON_UNMOUNT:-yes}"
  export TAPE_WEBHOOK_ENABLED="${TAPE_WEBHOOK_ENABLED:-false}"
  export TAPE_WEBHOOK_TOKEN="${TAPE_WEBHOOK_TOKEN:-}"
  export TAPE_WEBHOOK_LISTEN_ADDRESS="${TAPE_WEBHOOK_LISTEN_ADDRESS:-0.0.0.0}"
  export TAPE_WEBHOOK_PORT="${TAPE_WEBHOOK_PORT:-9080}"
  export TAPE_COMMAND_TIMEOUT="${TAPE_COMMAND_TIMEOUT:-180}"
  export TAPE_SET_BLOCK_SIZE="${TAPE_SET_BLOCK_SIZE:-yes}"
  export TAPE_BLOCK_SIZE="${TAPE_BLOCK_SIZE:-0}"
}

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

validate_number() {
  local name="$1" minimum="$2" maximum="$3"
  local value="${!name}"
  [[ "$value" =~ ^[0-9]{1,8}$ ]] || fail "Invalid $name"
  value=$((10#$value))
  (( value >= minimum && value <= maximum )) || fail "Invalid $name"
  export "$name=$value"
}

normalize_boolean() {
  local name="$1"
  local value="${!name}"
  case "${value,,}" in
    yes|true|1) export "$name=$2" ;;
    no|false|0) export "$name=$3" ;;
    *) fail "Invalid $name" ;;
  esac
}

validate_settings() {
  local name value
  local safe_text='^[a-zA-Z0-9_./ -]+$'

  for name in BAREOS_DIR_HOSTNAME BAREOS_DIR_PASSWORD BAREOS_STORAGE_NAME; do
    [[ -n "${!name:-}" ]] || fail "Missing $name"
    export "$name"
  done

  # These values go inside quoted Bareos fields. Reject configuration syntax.
  for name in BAREOS_DIR_HOSTNAME BAREOS_STORAGE_NAME BAREOS_STORAGE_DEVICE_NAME \
              BAREOS_MEDIA_TYPE TAPE_DEVICE BAREOS_SPOOL_DIRECTORY; do
    [[ "${!name}" =~ $safe_text ]] || fail "Invalid $name"
  done
  [[ "$TAPE_DEVICE" == /dev/* && "$TAPE_DEVICE/" != */../* ]] || fail "Invalid TAPE_DEVICE"
  [[ "$BAREOS_SPOOL_DIRECTORY" == /* && "$BAREOS_SPOOL_DIRECTORY/" != */../* ]] || fail "Invalid BAREOS_SPOOL_DIRECTORY"
  [[ "$BAREOS_MAXIMUM_SPOOL_SIZE" =~ ^[0-9]+([KkMmGgTtPp][Bb]?)?$ ]] || fail "Invalid BAREOS_MAXIMUM_SPOOL_SIZE"
  [[ "$TAPE_WEBHOOK_LISTEN_ADDRESS" =~ ^[0-9a-fA-F:.]+$ ]] || fail "Invalid TAPE_WEBHOOK_LISTEN_ADDRESS"

  validate_number BAREOS_STORAGE_PORT 1 65535
  validate_number BAREOS_DEBUG_LEVEL 0 1000
  validate_number TAPE_WEBHOOK_PORT 1 65535
  validate_number TAPE_COMMAND_TIMEOUT 1 3600
  validate_number TAPE_BLOCK_SIZE 0 16777216
  validate_number BAREOS_MAXIMUM_CONCURRENT_JOBS 1 100
  for name in BAREOS_MAXIMUM_CHANGER_WAIT BAREOS_MAXIMUM_REWIND_WAIT BAREOS_MAXIMUM_OPEN_WAIT; do
    validate_number "$name" 1 86400
  done
  for name in BAREOS_AUTOMATIC_MOUNT BAREOS_ALWAYS_OPEN BAREOS_OFFLINE_ON_UNMOUNT; do
    normalize_boolean "$name" yes no
  done
  for name in TAPE_WEBHOOK_ENABLED TAPE_SET_BLOCK_SIZE; do
    normalize_boolean "$name" true false
  done

  if [[ "$TAPE_WEBHOOK_ENABLED" == true ]]; then
    [[ "$TAPE_WEBHOOK_TOKEN" =~ ^[a-zA-Z0-9_-]{32,}$ ]] || fail "TAPE_WEBHOOK_TOKEN needs at least 32 letters, digits, underscores or hyphens"
    [[ "$TAPE_WEBHOOK_PORT" != "$BAREOS_STORAGE_PORT" ]] || fail "Webhook and Bareos ports must differ"
  else
    export TAPE_WEBHOOK_TOKEN=""
  fi

  # envsubst does not escape values. Escape the password for its quoted field.
  [[ ! "$BAREOS_DIR_PASSWORD" =~ [[:cntrl:]] ]] || fail "BAREOS_DIR_PASSWORD contains control characters"
  value="${BAREOS_DIR_PASSWORD//\\/\\\\}"
  export BAREOS_DIR_PASSWORD_ESCAPED="${value//\"/\\\"}"
}

render_configuration() {
  local templates="$1" config_dir="$2" runtime_dir="$3"
  umask 077
  mkdir -p "$config_dir/director" "$config_dir/storage" "$config_dir/device" "$runtime_dir"
  chmod 700 "$runtime_dir"

  envsubst '${BAREOS_DIR_HOSTNAME} ${BAREOS_DIR_PASSWORD_ESCAPED}' \
    < "$templates/director.conf.template" > "$config_dir/director/bareos-dir.conf"
  envsubst '${BAREOS_STORAGE_NAME} ${BAREOS_STORAGE_PORT}' \
    < "$templates/storage.conf.template" > "$config_dir/storage/bareos-sd.conf"
  envsubst '${BAREOS_STORAGE_DEVICE_NAME} ${BAREOS_MEDIA_TYPE} ${TAPE_DEVICE}
    ${BAREOS_AUTOMATIC_MOUNT} ${BAREOS_ALWAYS_OPEN} ${BAREOS_OFFLINE_ON_UNMOUNT}
    ${BAREOS_MAXIMUM_CHANGER_WAIT} ${BAREOS_MAXIMUM_REWIND_WAIT} ${BAREOS_MAXIMUM_OPEN_WAIT}
    ${BAREOS_SPOOL_DIRECTORY} ${BAREOS_MAXIMUM_SPOOL_SIZE} ${BAREOS_MAXIMUM_CONCURRENT_JOBS}' \
    < "$templates/device.conf.template" > "$config_dir/device/device-lto.conf"
  envsubst '${TAPE_WEBHOOK_TOKEN}' \
    < "$templates/hooks.json.template" > "$runtime_dir/hooks.json"

  chmod 600 "$config_dir/director/bareos-dir.conf" "$config_dir/storage/bareos-sd.conf" \
    "$config_dir/device/device-lto.conf" "$runtime_dir/hooks.json"
}

main() {
  set_defaults
  validate_settings
  echo "[entrypoint] Rendering Bareos configuration"
  render_configuration /etc/bareos-tape/templates /etc/bareos/bareos-sd.d /run/tape-webhook
  mkdir -p "$BAREOS_SPOOL_DIRECTORY"
  echo "[entrypoint] Validating Bareos configuration"
  /usr/sbin/bareos-sd -t || fail "Bareos configuration validation failed; see diagnostics above"

  if [[ "$TAPE_SET_BLOCK_SIZE" == true ]]; then
    echo "[entrypoint] Setting tape block size on $TAPE_DEVICE (timeout ${TAPE_COMMAND_TIMEOUT}s)"
    /usr/bin/timeout --kill-after=5 "$TAPE_COMMAND_TIMEOUT" \
      /usr/bin/mt -f "$TAPE_DEVICE" defblksize "$TAPE_BLOCK_SIZE" \
      || fail "Tape block-size setup failed; check device mapping and drive state, or set TAPE_SET_BLOCK_SIZE=no to skip this operation"
  fi

  echo "[entrypoint] Starting Supervisor (Bareos debug level $BAREOS_DEBUG_LEVEL)"
  exec /usr/bin/supervisord -c /etc/bareos-tape/supervisord.conf
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main
fi
