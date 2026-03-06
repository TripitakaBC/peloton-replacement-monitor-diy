#!/bin/bash
# Peloton Apps Update Script
# Updates: Spotify, Spicetify, FreeTube, Plex HTPC
# Reapplies Spicetify and fixes permissions for multi-user access
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }

echo "=============================="
echo " Peloton Apps Updater"
echo "=============================="

# Spotify (apt)
echo "--- Spotify ---"
sudo apt update -qq 2>/dev/null
sudo apt install --only-upgrade -y spotify-client 2>/dev/null && info "Spotify updated" || warn "Already latest"

# Spicetify
echo "--- Spicetify ---"
SPICETIFY="$HOME/.spicetify/spicetify"
if [ -x "$SPICETIFY" ]; then
    $SPICETIFY upgrade 2>/dev/null || warn "Already latest"
    sudo chown -R $(whoami) /usr/share/spotify/
    $SPICETIFY restore -n 2>/dev/null
    $SPICETIFY backup apply -n 2>/dev/null && info "Spicetify applied" || warn "Spicetify apply failed"
fi

# Fix Spotify permissions (critical for multi-user)
echo "--- Fixing Spotify permissions ---"
sudo chown -R root:root /usr/share/spotify/
sudo chmod -R a+rX /usr/share/spotify/
info "Permissions fixed"

# FreeTube (Flatpak)
echo "--- FreeTube ---"
flatpak update -y io.freetubeapp.FreeTube 2>/dev/null && info "FreeTube updated" || warn "Already latest"

# Plex HTPC (Flatpak)
echo "--- Plex HTPC ---"
flatpak update -y tv.plex.PlexHTPC 2>/dev/null && info "Plex HTPC updated" || warn "Already latest"

echo "=============================="
echo " Update complete!"
echo "=============================="
