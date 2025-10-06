#!/bin/bash

# Blinkr Collection Dashboard Update Script

set -e

echo "🔄 Updating Blinkr Collection Dashboard..."

# Pull latest images
docker-compose pull

# Rebuild and restart services
docker-compose up -d --build

# Run migrations
docker-compose exec web python manage.py migrate --settings=blinkr_dashboard.settings_production

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput --settings=blinkr_dashboard.settings_production

echo "✅ Update completed successfully!"
