# File Name: Dockerfile
# Purpose: Build Bareos tape storage with optional fixed HTTP tape controls.
# Overview: Preserves Debian Bookworm and the existing Bareos package source,
# adding the packaged webhook server, Supervisor, and a restricted mt helper.
FROM debian:bookworm

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg apt-transport-https ca-certificates && \
    rm -rf /var/lib/apt/lists/*
RUN wget https://download.bareos.org/current/Debian_12/add_bareos_repositories.sh && \
    chmod +x add_bareos_repositories.sh && ./add_bareos_repositories.sh
RUN apt-get update && apt-get install -y --no-install-recommends \
    bareos-storage bareos-tools bareos-storage-tape \
    mt-st mtx lsscsi sg3-utils smartmontools \
    webhook supervisor python3 psmisc gettext-base && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh tape-control.py /usr/local/bin/
COPY templates/ /etc/bareos-tape/templates/
COPY supervisord.conf /etc/bareos-tape/supervisord.conf
RUN chmod 755 /usr/local/bin/entrypoint.sh /usr/local/bin/tape-control.py
# Listener ports are runtime settings. Publish matching ports with -p or Compose.
VOLUME ["/data"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
