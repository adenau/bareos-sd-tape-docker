# Bareos SD Docker

## Overview
This repository provides a Dockerized implementation of the Bareos Storage Daemon (SD). It simplifies the deployment and configuration of the Bareos SD, enabling dynamic configuration using environment variables. This container is designed to handle backups seamlessly as part of the Bareos ecosystem.

## Why This Exists
Installing Bareos SD directly on a host system can be cumbersome and may not suit containerized environments. This repository provides:

- A clean, containerized implementation of Bareos SD.
- Dynamic configuration of the storage daemon and devices using environment variables.
- Easy scalability and portability.

## Features
- Dynamically expose the storage daemon port.
- Generate multiple device configurations based on user input.
- Fully customizable via environment variables.

## How to Use

### Pull the Docker Image
Pull the prebuilt Docker image (replace `<username>` with your GitHub username):
```bash
docker pull ghcr.io/adenau/bareos-sd-docker:latest
```

### Run the Container
To run the container, supply the mandatory environment variables and optional parameters:
```bash
docker run -d \
  -e BAREOS_DIR_HOSTNAME="bareos-dir" \
  -e BAREOS_DIR_PASSWORD="mypassword" \
  -e BAREOS_DIR_ADDRESS="10.0.1.204" \
  -e BAREOS_STORAGE_NAME="my-storage" \
  -e BAREOS_STORAGE_PORT="9103" \
  -e BAREOS_STORAGE_DEVICE_NAME="File-Metroplex" \
  -e BAREOS_STORAGE_DEVICE_NO="3" \
  -v /path_to_archive:/data \
  ghcr.io/<username>/bareos-sd-docker:latest
```

### Mandatory Environment Variables
| Variable                 | Description                                    | Example Value       |
|--------------------------|------------------------------------------------|---------------------|
| `BAREOS_DIR_HOSTNAME`    | The name of the Bareos Director               | `bareos-dir`        |
| `BAREOS_DIR_PASSWORD`    | Password for authenticating with the Director | `mypassword`        |
| `BAREOS_DIR_ADDRESS`     | IP address or hostname of the Director        | `10.0.1.204`        |
| `BAREOS_STORAGE_NAME`    | The name of the storage unit                  | `my-storage`        |
| `BAREOS_STORAGE_PORT`    | The port used by the storage daemon           | `9103`              |
| `BAREOS_STORAGE_DEVICE_NAME` | Base name for the storage devices          | `File-Storage`    |
| `BAREOS_STORAGE_DEVICE_NO`  | Number of storage devices to configure      | `3`                 |

## Configuration File Examples

### Director Configuration (`bareos-dir.conf`)
Generated dynamically:
```plaintext
Director {
  Name = bareos-dir
  Password = mypassword
}
```

### Storage Configuration (`myself.conf`)
Generated dynamically:
```plaintext
Storage {
  Name = my-storage
  SD Port = 9103
  Media Type = File
}
```

### Device Configuration (`device-<count>.conf`)
Generated dynamically for each device:
```plaintext
Device {
  Name = File-Metroplex-1
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
```

## Development
To build the image locally:
```bash
docker build -t bareos-sd-docker .
```

## License
This project is licensed under the MIT License. See the `LICENSE` file for details.

