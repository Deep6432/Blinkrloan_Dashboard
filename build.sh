#!/bin/bash

# Blinkr Collection Dashboard - Production Build Script
# This script creates a complete production build package

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BUILD_DIR="build"
BUILD_NAME="blinkr-dashboard-build"
VERSION=$(date +"%Y%m%d-%H%M%S")
BUILD_PACKAGE="${BUILD_NAME}-${VERSION}.tar.gz"

echo -e "${GREEN}🏗️  Building Blinkr Collection Dashboard Production Package${NC}"
echo -e "${BLUE}Version: ${VERSION}${NC}"
echo -e "${BLUE}Build Directory: ${BUILD_DIR}${NC}"

# Clean previous builds
if [ -d "$BUILD_DIR" ]; then
    echo -e "\n${YELLOW}🧹 Cleaning previous build...${NC}"
    rm -rf "$BUILD_DIR"
fi

# Create build directory structure
echo -e "\n${YELLOW}📁 Creating build directory structure...${NC}"
mkdir -p "$BUILD_DIR"/{app,config,scripts,docs}

# Copy application files
echo -e "\n${YELLOW}📦 Copying application files...${NC}"
cp -r blinkr_dashboard "$BUILD_DIR/app/"
cp -r dashboard "$BUILD_DIR/app/"
cp -r templates "$BUILD_DIR/app/"
cp -r static "$BUILD_DIR/app/"
cp manage.py "$BUILD_DIR/app/"
cp requirements.txt "$BUILD_DIR/app/"
cp requirements_production.txt "$BUILD_DIR/app/"

# Copy configuration files
echo -e "\n${YELLOW}⚙️  Copying configuration files...${NC}"
cp Dockerfile "$BUILD_DIR/"
cp docker-compose.yml "$BUILD_DIR/"
cp nginx.conf "$BUILD_DIR/"
cp env.example "$BUILD_DIR/"
cp blinkr_dashboard/settings_production.py "$BUILD_DIR/config/"

# Copy deployment scripts
echo -e "\n${YELLOW}🚀 Copying deployment scripts...${NC}"
cp deploy-aws.sh "$BUILD_DIR/scripts/"
cp setup-env.sh "$BUILD_DIR/scripts/"
cp ecs-task-definition.json "$BUILD_DIR/scripts/"
cp cloudformation-template.json "$BUILD_DIR/scripts/"

# Copy documentation
echo -e "\n${YELLOW}📚 Copying documentation...${NC}"
cp DEPLOYMENT.md "$BUILD_DIR/docs/"
cp PRODUCTION_BUILD.md "$BUILD_DIR/docs/"
cp README.md "$BUILD_DIR/docs/"

# Create build configuration
echo -e "\n${YELLOW}📋 Creating build configuration...${NC}"
cat > "$BUILD_DIR/build-info.json" << EOF
{
  "name": "Blinkr Collection Dashboard",
  "version": "${VERSION}",
  "build_date": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "build_type": "production",
  "components": {
    "django_app": "4.2.7",
    "database": "postgresql",
    "cache": "redis",
    "web_server": "nginx",
    "container_platform": "docker"
  },
  "deployment_targets": [
    "aws_ecs",
    "aws_ec2",
    "docker_compose"
  ]
}
EOF

# Create deployment instructions
echo -e "\n${YELLOW}📝 Creating deployment instructions...${NC}"
cat > "$BUILD_DIR/DEPLOY_INSTRUCTIONS.md" << 'EOF'
# Blinkr Collection Dashboard - Deployment Instructions

## Quick Start

### 1. Environment Setup
```bash
# Copy environment template
cp env.example .env

# Edit with your values
nano .env
```

### 2. Docker Deployment (Recommended)
```bash
# Build and start services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 3. AWS ECS Deployment
```bash
# Make scripts executable
chmod +x scripts/*.sh

# Run setup
./scripts/setup-env.sh

# Deploy to AWS
./scripts/deploy-aws.sh
```

### 4. Manual AWS Setup
```bash
# Deploy infrastructure
aws cloudformation create-stack \
  --stack-name blinkr-dashboard \
  --template-body file://scripts/cloudformation-template.json \
  --parameters ParameterKey=DatabasePassword,ParameterValue=your-password \
              ParameterKey=SecretKey,ParameterValue=your-secret-key \
  --capabilities CAPABILITY_IAM
```

## Configuration

### Required Environment Variables
- `SECRET_KEY`: Django secret key
- `DB_PASSWORD`: Database password
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `EXTERNAL_API_URL`: External API endpoint

### Optional Environment Variables
- `DEBUG`: Set to False for production
- `REDIS_URL`: Redis connection string
- `EMAIL_*`: Email configuration
- `AWS_*`: AWS credentials for deployment

## Health Checks

- Application: `http://your-domain/health/`
- API: `http://your-domain/api/kpi-data/`
- Dashboard: `http://your-domain/dashboard/`

## Monitoring

- Logs: Check Docker logs or CloudWatch
- Metrics: ECS service metrics
- Database: RDS performance insights

## Support

For issues, check:
1. Application logs
2. Docker/ECS service status
3. Database connectivity
4. External API availability
EOF

# Create startup script
echo -e "\n${YELLOW}🚀 Creating startup script...${NC}"
cat > "$BUILD_DIR/start.sh" << 'EOF'
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
EOF

chmod +x "$BUILD_DIR/start.sh"

# Create stop script
echo -e "\n${YELLOW}🛑 Creating stop script...${NC}"
cat > "$BUILD_DIR/stop.sh" << 'EOF'
#!/bin/bash

# Blinkr Collection Dashboard Stop Script

echo "🛑 Stopping Blinkr Collection Dashboard..."

# Stop all services
docker-compose down

echo "✅ All services stopped."
EOF

chmod +x "$BUILD_DIR/stop.sh"

# Create update script
echo -e "\n${YELLOW}🔄 Creating update script...${NC}"
cat > "$BUILD_DIR/update.sh" << 'EOF'
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
EOF

chmod +x "$BUILD_DIR/update.sh"

# Create health check script
echo -e "\n${YELLOW}🏥 Creating health check script...${NC}"
cat > "$BUILD_DIR/health-check.sh" << 'EOF'
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
EOF

chmod +x "$BUILD_DIR/health-check.sh"

# Create backup script
echo -e "\n${YELLOW}💾 Creating backup script...${NC}"
cat > "$BUILD_DIR/backup.sh" << 'EOF'
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
EOF

chmod +x "$BUILD_DIR/backup.sh"

# Create restore script
echo -e "\n${YELLOW}🔄 Creating restore script...${NC}"
cat > "$BUILD_DIR/restore.sh" << 'EOF'
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
EOF

chmod +x "$BUILD_DIR/restore.sh"

# Create package
echo -e "\n${YELLOW}📦 Creating deployment package...${NC}"
tar -czf "$BUILD_PACKAGE" -C "$BUILD_DIR" .

# Calculate package size
PACKAGE_SIZE=$(du -h "$BUILD_PACKAGE" | cut -f1)

# Create package info
echo -e "\n${GREEN}✅ Build completed successfully!${NC}"
echo -e "${BLUE}📦 Package: ${BUILD_PACKAGE}${NC}"
echo -e "${BLUE}📏 Size: ${PACKAGE_SIZE}${NC}"
echo -e "${BLUE}📁 Build Directory: ${BUILD_DIR}/${NC}"

# Display package contents
echo -e "\n${YELLOW}📋 Package Contents:${NC}"
tar -tzf "$BUILD_PACKAGE" | head -20
if [ $(tar -tzf "$BUILD_PACKAGE" | wc -l) -gt 20 ]; then
    echo "... and $(($(tar -tzf "$BUILD_PACKAGE" | wc -l) - 20)) more files"
fi

# Display usage instructions
echo -e "\n${YELLOW}🚀 Usage Instructions:${NC}"
echo -e "${BLUE}1. Extract the package:${NC}"
echo -e "   tar -xzf ${BUILD_PACKAGE}"
echo -e "\n${BLUE}2. Configure environment:${NC}"
echo -e "   cp env.example .env"
echo -e "   nano .env"
echo -e "\n${BLUE}3. Start the application:${NC}"
echo -e "   ./start.sh"
echo -e "\n${BLUE}4. Check health:${NC}"
echo -e "   ./health-check.sh"

echo -e "\n${GREEN}🎉 Production build package ready for deployment!${NC}"
