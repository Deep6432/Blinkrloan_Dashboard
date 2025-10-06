#!/bin/bash

# Blinkr Collection Dashboard Restore Script

set -e

if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup-file>"
    echo "Available backups:"
    ls -la backups/
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "🔄 Restoring from backup: $BACKUP_FILE"

# Extract backup
TEMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"

# Restore database
echo "🗄️  Restoring database..."
docker-compose exec -T db psql -U postgres -d blinkr_dashboard < "$TEMP_DIR/database-"*.sql

# Restore media files
echo "📁 Restoring media files..."
if [ -f "$TEMP_DIR/media-"*.tar.gz ]; then
    tar -xzf "$TEMP_DIR/media-"*.tar.gz
fi

# Restore configuration
echo "⚙️  Restoring configuration..."
tar -xzf "$TEMP_DIR/config-"*.tar.gz

# Clean up
rm -rf "$TEMP_DIR"

echo "✅ Restore completed successfully!"
