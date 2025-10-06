#!/bin/bash

# Blinkr Collection Dashboard Stop Script

echo "🛑 Stopping Blinkr Collection Dashboard..."

# Stop all services
docker-compose down

echo "✅ All services stopped."
