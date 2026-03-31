#!/bin/sh
# Docker entrypoint for Asterisk:
# 1. Substitute env vars into config templates (source: /etc/asterisk-src)
# 2. Copy AGI scripts to /var/lib/asterisk/agi-bin
# 3. Start Asterisk

set -e

SRC=/etc/asterisk-src
DST=/etc/asterisk

echo "Generating Asterisk configs from templates..."
mkdir -p "$DST"

for f in "$SRC"/*.conf; do
    base=$(basename "$f")
    envsubst < "$f" > "$DST/$base"
    echo "  wrote $DST/$base"
done

# Copy AGI scripts from mounted /etc/asterisk-agi
mkdir -p /var/lib/asterisk/agi-bin
cp /etc/asterisk-agi/*.agi /var/lib/asterisk/agi-bin/ 2>/dev/null || true
chmod +x /var/lib/asterisk/agi-bin/*.agi 2>/dev/null || true

echo "Starting Asterisk..."
exec asterisk -f -vvv
