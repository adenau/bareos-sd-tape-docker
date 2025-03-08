#!/bin/bash

# Exit immediately if a command exits with a non-zero status
set -e

# Default configuration file paths
CONFIG_DIR=/etc/bareos/bareos-sd.d
DIRECTOR_CONF=$CONFIG_DIR/director/bareos-dir.conf
STORAGE_CONF=$CONFIG_DIR/storage/bareos-sd.conf
DEVICE_CONF_DIR=$CONFIG_DIR/device

# Validate required environment variables
if [ -z "$BAREOS_DIR_HOSTNAME" ] || [ -z "$BAREOS_DIR_PASSWORD" ] || \
   [ -z "$BAREOS_DIR_ADDRESS" ] || [ -z "$BAREOS_STORAGE_NAME" ] || \
   [ -z "$BAREOS_STORAGE_PORT" ] || [ -z "$BAREOS_STORAGE_DEVICE_NO" ]; then
  echo "ERROR: Missing one or more required environment variables."
  echo "Ensure BAREOS_DIR_HOSTNAME, BAREOS_DIR_PASSWORD, BAREOS_DIR_ADDRESS,"
  echo "BAREOS_STORAGE_NAME, BAREOS_STORAGE_PORT, and BAREOS_STORAGE_DEVICE_NO are set."
  exit 1
fi

# Generate the director configuration file
mkdir -p $(dirname "$DIRECTOR_CONF")
echo "Generating $DIRECTOR_CONF..."
cat > "$DIRECTOR_CONF" <<EOF
Director {
  Name = $BAREOS_DIR_HOSTNAME
  Password = $BAREOS_DIR_PASSWORD
}
EOF

# Generate the storage configuration file
mkdir -p $(dirname "$STORAGE_CONF")
echo "Generating $STORAGE_CONF..."
cat > "$STORAGE_CONF" <<EOF
Storage {
  Name = $BAREOS_STORAGE_NAME
  SD Port = $BAREOS_STORAGE_PORT
}
EOF

# Generate the device configuration files
mkdir -p "$DEVICE_CONF_DIR"
echo "Generating device configurations in $DEVICE_CONF_DIR..."
for ((count=1; count<=$BAREOS_STORAGE_DEVICE_NO; count++)); do
  DEVICE_CONF="$DEVICE_CONF_DIR/device-$count.conf"
  cat > "$DEVICE_CONF" <<EOF
Device {
  Name = $BAREOS_STORAGE_DEVICE_NAME-$count
  Media Type = File
  Archive Device = /data
  LabelMedia = yes
  Random Access = yes
  AutomaticMount = yes
  RemovableMedia = no
  AlwaysOpen = no
  Description = "File device. A connecting Director must have the same Name and MediaType."
  Maximum Concurrent Jobs = 1
}

EOF
done

echo "Deleting extra FileStorage.conf file in $DEVICE_CONF_DIR..."
rm "$DEVICE_CONF_DIR/FileStorage.conf"

# Start the Bareos Storage Daemon
echo "Starting Bareos Storage Daemon..."
exec bareos-sd -f
