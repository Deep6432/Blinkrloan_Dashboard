#!/bin/bash

# AWS Deployment Script for Blinkr Collection Dashboard
# This script deploys the Django application to AWS using Docker

set -e

# Configuration
AWS_REGION="us-east-1"
ECR_REPOSITORY="blinkr-dashboard"
ECR_IMAGE_TAG="latest"
ECS_CLUSTER="blinkr-cluster"
ECS_SERVICE="blinkr-service"
ECS_TASK_DEFINITION="blinkr-task"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting AWS deployment for Blinkr Collection Dashboard${NC}"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Get AWS account ID
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

echo -e "${YELLOW}📋 Deployment Configuration:${NC}"
echo "  AWS Region: ${AWS_REGION}"
echo "  AWS Account ID: ${AWS_ACCOUNT_ID}"
echo "  ECR Repository: ${ECR_REPOSITORY}"
echo "  ECR URI: ${ECR_URI}"
echo "  ECS Cluster: ${ECS_CLUSTER}"
echo "  ECS Service: ${ECS_SERVICE}"

# Step 1: Create ECR repository if it doesn't exist
echo -e "\n${YELLOW}📦 Creating ECR repository...${NC}"
aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} 2>/dev/null || {
    echo "Creating ECR repository..."
    aws ecr create-repository --repository-name ${ECR_REPOSITORY} --region ${AWS_REGION}
}

# Step 2: Login to ECR
echo -e "\n${YELLOW}🔐 Logging into ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Step 3: Build Docker image
echo -e "\n${YELLOW}🔨 Building Docker image...${NC}"
docker build -t ${ECR_REPOSITORY}:${ECR_IMAGE_TAG} .

# Step 4: Tag image for ECR
echo -e "\n${YELLOW}🏷️  Tagging image for ECR...${NC}"
docker tag ${ECR_REPOSITORY}:${ECR_IMAGE_TAG} ${ECR_URI}:${ECR_IMAGE_TAG}

# Step 5: Push image to ECR
echo -e "\n${YELLOW}⬆️  Pushing image to ECR...${NC}"
docker push ${ECR_URI}:${ECR_IMAGE_TAG}

# Step 6: Update ECS service
echo -e "\n${YELLOW}🔄 Updating ECS service...${NC}"
aws ecs update-service \
    --cluster ${ECS_CLUSTER} \
    --service ${ECS_SERVICE} \
    --force-new-deployment \
    --region ${AWS_REGION}

echo -e "\n${GREEN}✅ Deployment completed successfully!${NC}"
echo -e "${YELLOW}📊 You can monitor the deployment in the AWS ECS console.${NC}"
echo -e "${YELLOW}🌐 Your application should be available at your configured domain.${NC}"
