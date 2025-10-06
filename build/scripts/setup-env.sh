#!/bin/bash

# Environment setup script for Blinkr Collection Dashboard
# This script helps set up the environment for production deployment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 Setting up environment for Blinkr Collection Dashboard${NC}"

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}📝 Creating .env file from template...${NC}"
    cp env.example .env
    echo -e "${YELLOW}⚠️  Please edit .env file with your actual values before proceeding.${NC}"
    echo -e "${YELLOW}   Key values to update:${NC}"
    echo -e "${YELLOW}   - SECRET_KEY: Generate a new secret key${NC}"
    echo -e "${YELLOW}   - DB_PASSWORD: Set your database password${NC}"
    echo -e "${YELLOW}   - ALLOWED_HOSTS: Add your domain name${NC}"
    echo -e "${YELLOW}   - AWS credentials if deploying to AWS${NC}"
    exit 1
fi

# Load environment variables
source .env

echo -e "${YELLOW}📋 Environment Configuration:${NC}"
echo "  DEBUG: ${DEBUG}"
echo "  DB_HOST: ${DB_HOST}"
echo "  DB_NAME: ${DB_NAME}"
echo "  REDIS_URL: ${REDIS_URL}"
echo "  EXTERNAL_API_URL: ${EXTERNAL_API_URL}"

# Create necessary directories
echo -e "\n${YELLOW}📁 Creating necessary directories...${NC}"
mkdir -p logs
mkdir -p staticfiles
mkdir -p media
mkdir -p ssl

# Set proper permissions
echo -e "\n${YELLOW}🔐 Setting proper permissions...${NC}"
chmod 755 logs
chmod 755 staticfiles
chmod 755 media
chmod 700 ssl

# Generate Django secret key if not set
if [ "$SECRET_KEY" = "your-super-secret-key-here-change-this-in-production" ]; then
    echo -e "\n${YELLOW}🔑 Generating new Django secret key...${NC}"
    NEW_SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    sed -i.bak "s/SECRET_KEY=your-super-secret-key-here-change-this-in-production/SECRET_KEY=${NEW_SECRET_KEY}/" .env
    echo -e "${GREEN}✅ New secret key generated and saved to .env${NC}"
fi

# Check if database is accessible
echo -e "\n${YELLOW}🗄️  Checking database connection...${NC}"
if command -v psql &> /dev/null; then
    if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1;" &> /dev/null; then
        echo -e "${GREEN}✅ Database connection successful${NC}"
    else
        echo -e "${RED}❌ Database connection failed. Please check your database configuration.${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  PostgreSQL client not found. Skipping database check.${NC}"
fi

# Check if Redis is accessible
echo -e "\n${YELLOW}🔴 Checking Redis connection...${NC}"
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✅ Redis connection successful${NC}"
    else
        echo -e "${RED}❌ Redis connection failed. Please check your Redis configuration.${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Redis client not found. Skipping Redis check.${NC}"
fi

# Run Django migrations
echo -e "\n${YELLOW}🔄 Running Django migrations...${NC}"
python manage.py migrate --settings=blinkr_dashboard.settings_production

# Collect static files
echo -e "\n${YELLOW}📦 Collecting static files...${NC}"
python manage.py collectstatic --noinput --settings=blinkr_dashboard.settings_production

# Create superuser if it doesn't exist
echo -e "\n${YELLOW}👤 Checking for superuser...${NC}"
if ! python manage.py shell --settings=blinkr_dashboard.settings_production -c "from django.contrib.auth.models import User; print('Superuser exists' if User.objects.filter(is_superuser=True).exists() else 'No superuser')" | grep -q "Superuser exists"; then
    echo -e "${YELLOW}⚠️  No superuser found. You may want to create one:${NC}"
    echo -e "${YELLOW}   python manage.py createsuperuser --settings=blinkr_dashboard.settings_production${NC}"
fi

echo -e "\n${GREEN}✅ Environment setup completed successfully!${NC}"
echo -e "${YELLOW}📋 Next steps:${NC}"
echo -e "${YELLOW}   1. Review and update .env file with your actual values${NC}"
echo -e "${YELLOW}   2. Create a superuser if needed${NC}"
echo -e "${YELLOW}   3. Test the application locally${NC}"
echo -e "${YELLOW}   4. Deploy to AWS using deploy-aws.sh${NC}"
