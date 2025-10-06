#!/bin/bash

# Blinkr Collection Dashboard Startup Script

set -e

echo "🚀 Starting Blinkr Collection Dashboard..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found. Please copy env.example to .env and configure it."
    exit 1
fi

# Load environment variables
source .env

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Build and start services
echo "📦 Building and starting services..."
docker-compose up -d --build

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service status
echo "📊 Service Status:"
docker-compose ps

# Run database migrations
echo "🗄️  Running database migrations..."
docker-compose exec web python manage.py migrate --settings=blinkr_dashboard.settings_production

# Collect static files
echo "📦 Collecting static files..."
docker-compose exec web python manage.py collectstatic --noinput --settings=blinkr_dashboard.settings_production

echo "✅ Blinkr Collection Dashboard is ready!"
echo "🌐 Access the dashboard at: http://localhost"
echo "📊 Health check: http://localhost/health/"
