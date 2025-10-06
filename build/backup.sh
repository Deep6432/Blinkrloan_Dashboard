#!/bin/bash

# Blinkr Collection Dashboard Backup Script

set -e

BACKUP_DIR="backups"
TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
BACKUP_FILE="blinkr-backup-${TIMESTAMP}.tar.gz"

echo "💾 Creating backup..."

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
echo "🗄️  Backing up database..."
docker-compose exec -T db pg_dump -U postgres blinkr_dashboard > "$BACKUP_DIR/database-${TIMESTAMP}.sql"

# Backup media files
echo "📁 Backing up media files..."
if [ -d "media" ]; then
    tar -czf "$BACKUP_DIR/media-${TIMESTAMP}.tar.gz" media/
fi

# Backup configuration
echo "⚙️  Backing up configuration..."
tar -czf "$BACKUP_DIR/config-${TIMESTAMP}.tar.gz" .env docker-compose.yml nginx.conf

# Create complete backup
echo "📦 Creating complete backup..."
tar -czf "$BACKUP_DIR/$BACKUP_FILE" "$BACKUP_DIR/database-${TIMESTAMP}.sql" "$BACKUP_DIR/media-${TIMESTAMP}.tar.gz" "$BACKUP_DIR/config-${TIMESTAMP}.tar.gz"

# Clean up individual files
rm "$BACKUP_DIR/database-${TIMESTAMP}.sql" "$BACKUP_DIR/media-${TIMESTAMP}.tar.gz" "$BACKUP_DIR/config-${TIMESTAMP}.tar.gz"

echo "✅ Backup created: $BACKUP_DIR/$BACKUP_FILE"
