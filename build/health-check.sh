#!/bin/bash

# Blinkr Collection Dashboard Health Check Script

echo "🏥 Checking Blinkr Collection Dashboard Health..."

# Check if services are running
if ! docker-compose ps | grep -q "Up"; then
    echo "❌ Services are not running"
    exit 1
fi

# Check application health
if curl -f http://localhost/health/ &> /dev/null; then
    echo "✅ Application health check passed"
else
    echo "❌ Application health check failed"
    exit 1
fi

# Check API endpoint
if curl -f http://localhost/api/kpi-data/ &> /dev/null; then
    echo "✅ API health check passed"
else
    echo "❌ API health check failed"
    exit 1
fi

echo "✅ All health checks passed!"
