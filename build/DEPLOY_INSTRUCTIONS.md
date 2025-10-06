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
