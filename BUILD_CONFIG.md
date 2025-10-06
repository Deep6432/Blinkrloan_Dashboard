# Build Configuration for Blinkr Collection Dashboard

## Build Information
- **Project**: Blinkr Collection Dashboard
- **Version**: 1.0.0
- **Build Date**: $(date)
- **Build Type**: Production

## Build Components
- Django Application (4.2.7)
- PostgreSQL Database
- Redis Cache
- Nginx Web Server
- Docker Containerization

## Build Scripts
- `build.sh` - Main build script
- `start.sh` - Application startup
- `stop.sh` - Application shutdown
- `update.sh` - Application update
- `health-check.sh` - Health monitoring
- `backup.sh` - Data backup
- `restore.sh` - Data restore

## Deployment Targets
- AWS ECS (Elastic Container Service)
- AWS EC2 (Elastic Compute Cloud)
- Docker Compose (Local/On-premise)

## Build Output
- `blinkr-dashboard-build-{timestamp}.tar.gz` - Complete deployment package
- `build/` - Build directory with all components

## Usage
```bash
# Create build
./build.sh

# Extract and deploy
tar -xzf blinkr-dashboard-build-*.tar.gz
cp env.example .env
# Edit .env with your configuration
./start.sh
```
