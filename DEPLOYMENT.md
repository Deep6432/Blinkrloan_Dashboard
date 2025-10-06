# Blinkr Collection Dashboard - AWS Deployment Guide

This guide will help you deploy the Blinkr Collection Dashboard to AWS using Docker containers and ECS (Elastic Container Service).

## 📋 Prerequisites

Before deploying, ensure you have the following:

### Required Tools
- [AWS CLI](https://aws.amazon.com/cli/) installed and configured
- [Docker](https://www.docker.com/) installed and running
- [Git](https://git-scm.com/) for version control
- Python 3.10+ for local development

### AWS Account Setup
- AWS account with appropriate permissions
- ECR (Elastic Container Registry) access
- ECS (Elastic Container Service) access
- RDS (Relational Database Service) access
- ElastiCache access
- VPC with public and private subnets

## 🚀 Quick Start Deployment

### 1. Environment Setup

```bash
# Clone the repository
git clone https://github.com/Deep6432/Blinkrloan_Dashboard.git
cd Blinkrloan_Dashboard

# Run environment setup
./setup-env.sh
```

### 2. Configure Environment Variables

Edit the `.env` file with your actual values:

```bash
# Required settings
SECRET_KEY=your-generated-secret-key
DB_PASSWORD=your-secure-database-password
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# AWS settings
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
```

### 3. Deploy to AWS

```bash
# Make deployment script executable
chmod +x deploy-aws.sh

# Deploy to AWS
./deploy-aws.sh
```

## 🏗️ Infrastructure Setup

### Option 1: Using CloudFormation (Recommended)

1. **Update the CloudFormation template**:
   - Edit `cloudformation-template.json`
   - Replace `YOUR_ACCOUNT_ID` with your AWS account ID
   - Update VPC and subnet IDs

2. **Deploy the infrastructure**:
   ```bash
   aws cloudformation create-stack \
     --stack-name blinkr-dashboard \
     --template-body file://cloudformation-template.json \
     --parameters ParameterKey=DatabasePassword,ParameterValue=your-db-password \
                 ParameterKey=SecretKey,ParameterValue=your-secret-key \
     --capabilities CAPABILITY_IAM
   ```

### Option 2: Manual Setup

#### 1. Create ECR Repository
```bash
aws ecr create-repository --repository-name blinkr-dashboard --region us-east-1
```

#### 2. Create RDS Database
```bash
aws rds create-db-instance \
  --db-instance-identifier blinkr-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 13.7 \
  --master-username postgres \
  --master-user-password your-db-password \
  --allocated-storage 20 \
  --vpc-security-group-ids sg-your-security-group \
  --db-subnet-group-name your-db-subnet-group
```

#### 3. Create ElastiCache Redis
```bash
aws elasticache create-replication-group \
  --replication-group-id blinkr-redis \
  --description "Redis cluster for Blinkr Dashboard" \
  --node-type cache.t3.micro \
  --num-cache-clusters 1 \
  --engine redis
```

#### 4. Create ECS Cluster
```bash
aws ecs create-cluster --cluster-name blinkr-cluster
```

## 🐳 Docker Configuration

### Build and Test Locally

```bash
# Build the Docker image
docker build -t blinkr-dashboard .

# Run with docker-compose
docker-compose up -d

# Test the application
curl http://localhost:8000/health/
```

### Production Docker Image

The Dockerfile includes:
- Python 3.10 slim base image
- PostgreSQL client
- Security hardening
- Non-root user
- Health checks
- Static file collection

## 🔧 Configuration Files

### Production Settings (`settings_production.py`)
- Debug mode disabled
- PostgreSQL database configuration
- Redis caching
- Security headers
- Logging configuration
- Static file handling

### Nginx Configuration (`nginx.conf`)
- Load balancing
- Rate limiting
- Security headers
- Static file serving
- SSL/TLS support (when configured)

### Docker Compose (`docker-compose.yml`)
- Multi-service setup
- Database and Redis services
- Nginx reverse proxy
- Volume management

## 🔐 Security Considerations

### Environment Variables
- Never commit `.env` files to version control
- Use AWS Systems Manager Parameter Store for secrets
- Rotate secrets regularly

### Network Security
- Use private subnets for databases
- Configure security groups properly
- Enable VPC Flow Logs

### Application Security
- Enable HTTPS in production
- Configure CORS properly
- Use security headers
- Implement rate limiting

## 📊 Monitoring and Logging

### CloudWatch Logs
- Application logs are sent to CloudWatch
- Log group: `/ecs/blinkr-dashboard`
- Retention: 30 days

### Health Checks
- Application health endpoint: `/health/`
- ECS health checks configured
- Load balancer health checks

### Metrics
- ECS service metrics
- Application Load Balancer metrics
- RDS performance insights
- ElastiCache metrics

## 🚨 Troubleshooting

### Common Issues

#### 1. Database Connection Errors
```bash
# Check database connectivity
aws rds describe-db-instances --db-instance-identifier blinkr-db

# Verify security groups
aws ec2 describe-security-groups --group-ids sg-your-db-sg
```

#### 2. ECS Task Failures
```bash
# Check task logs
aws logs get-log-events --log-group-name /ecs/blinkr-dashboard --log-stream-name ecs/blinkr-dashboard/your-task-id

# Describe failed tasks
aws ecs describe-tasks --cluster blinkr-cluster --tasks your-task-arn
```

#### 3. Load Balancer Issues
```bash
# Check target group health
aws elbv2 describe-target-health --target-group-arn your-target-group-arn

# Check load balancer status
aws elbv2 describe-load-balancers --load-balancer-arns your-alb-arn
```

### Debug Commands

```bash
# Check ECS service status
aws ecs describe-services --cluster blinkr-cluster --services blinkr-service

# View recent events
aws ecs describe-services --cluster blinkr-cluster --services blinkr-service --query 'services[0].events'

# Check task definition
aws ecs describe-task-definition --task-definition blinkr-task
```

## 🔄 CI/CD Pipeline

### GitHub Actions (Optional)

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v1
      with:
        aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
        aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        aws-region: us-east-1
    
    - name: Login to Amazon ECR
      id: login-ecr
      uses: aws-actions/amazon-ecr-login@v1
    
    - name: Build, tag, and push image to Amazon ECR
      env:
        ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        ECR_REPOSITORY: blinkr-dashboard
        IMAGE_TAG: ${{ github.sha }}
      run: |
        docker build -t $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG .
        docker push $ECR_REGISTRY/$ECR_REPOSITORY:$IMAGE_TAG
    
    - name: Deploy to ECS
      run: |
        aws ecs update-service --cluster blinkr-cluster --service blinkr-service --force-new-deployment
```

## 📈 Scaling

### Horizontal Scaling
- Increase ECS service desired count
- Configure auto-scaling policies
- Use Application Load Balancer for distribution

### Vertical Scaling
- Increase task CPU/memory allocation
- Upgrade RDS instance class
- Increase ElastiCache node size

## 🔄 Backup and Recovery

### Database Backups
- RDS automated backups enabled
- Point-in-time recovery configured
- Cross-region backup replication

### Application Data
- Static files in S3
- Media files in S3
- Configuration in Parameter Store

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review AWS CloudWatch logs
3. Check ECS service events
4. Contact the development team

## 📝 License

This project is proprietary software. All rights reserved.

---

**Last Updated**: October 2025
**Version**: 1.0.0
