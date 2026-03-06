#!/bin/bash
# Proxmox Backup Server — Full System Backup
# Run with sudo: sudo ./pbs-backup.sh

# ── Configuration ─────────────────────────────────────────────────────
PBS_IP="<your-pbs-server-ip>"          # e.g., 192.168.1.100
PBS_USER="root@pam!<token-name>"       # PBS API token user
PBS_DATASTORE="<datastore-name>"       # PBS datastore name

export PBS_PASSWORD="<your-api-token>"
export PBS_FINGERPRINT="<your-server-fingerprint>"

# ── Backup Logic ──────────────────────────────────────────────────────
export PBS_REPOSITORY="$PBS_USER@$PBS_IP:$PBS_DATASTORE"

echo "Starting backup to $PBS_REPOSITORY..."

proxmox-backup-client backup root.pxar:/ \
    --exclude /dev \
    --exclude /proc \
    --exclude /sys \
    --exclude /tmp \
    --exclude /run \
    --exclude /mnt \
    --exclude /media \
    --exclude /lost+found

if [ $? -eq 0 ]; then
    echo "Backup completed successfully."
else
    echo "Backup FAILED."
    exit 1
fi
