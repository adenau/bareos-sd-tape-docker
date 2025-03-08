# Start with a base image
FROM debian:bookworm

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Update and install prerequisites for Bareos repository setup
RUN apt-get update && \
    apt-get install -y \
    wget \
    gnupg \
    apt-transport-https && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Add the Bareos repository and install Bareos Storage Daemon
RUN wget https://download.bareos.org/current/Debian_12/add_bareos_repositories.sh && \
    chmod +x add_bareos_repositories.sh && \
    ./add_bareos_repositories.sh && \
    apt-get update && \
    apt-get install -y bareos-storage && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Expose Bareos port dynamically
ENV BAREOS_STORAGE_PORT="9103"
EXPOSE $BAREOS_STORAGE_PORT

# Create directories for configuration and data
VOLUME ["/data"]

# Add entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Environment variables for configuration
ENV BAREOS_DIR_HOSTNAME="" \
    BAREOS_DIR_PASSWORD="" \
    BAREOS_DIR_ADDRESS="" \
    BAREOS_STORAGE_NAME="" \
    BAREOS_STORAGE_PORT="" \
    BAREOS_STORAGE_DEVICE_NAME="" \
    BAREOS_STORAGE_DEVICE_NO=""

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
