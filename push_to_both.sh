#!/bin/bash

# Script to push changes to both main and prod branches
# Usage: ./push_to_both.sh "commit message"

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if commit message is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Commit message is required${NC}"
    echo "Usage: ./push_to_both.sh \"Your commit message\""
    exit 1
fi

COMMIT_MSG="$1"
CURRENT_BRANCH=$(git branch --show-current)

echo -e "${YELLOW}Current branch: ${CURRENT_BRANCH}${NC}"

# Stash any uncommitted changes (excluding cache files and db)
echo -e "${YELLOW}Stashing uncommitted changes...${NC}"
git stash push -m "Auto-stash before push_to_both" -- \
    blinkr_dashboard/__pycache__/ \
    dashboard/__pycache__/ \
    db.sqlite3 \
    templates/dashboard/dashboard.html 2>/dev/null || true

# Add and commit changes (excluding cache and db)
echo -e "${YELLOW}Adding changes...${NC}"
git add dashboard/views.py templates/dashboard/dashboard.html 2>/dev/null || true

# Check if there are changes to commit
if git diff --staged --quiet; then
    echo -e "${YELLOW}No changes to commit${NC}"
else
    echo -e "${YELLOW}Committing changes...${NC}"
    git commit -m "$COMMIT_MSG"
fi

# Determine which branch we're on and push accordingly
if [ "$CURRENT_BRANCH" = "prod" ]; then
    echo -e "${GREEN}Pushing to prod branch...${NC}"
    git push edge_uat prod || git push origin prod
    
    echo -e "${YELLOW}Switching to main branch...${NC}"
    git checkout main
    
    echo -e "${YELLOW}Merging prod into main...${NC}"
    git merge prod -m "Merge prod into main: $COMMIT_MSG"
    
    echo -e "${GREEN}Pushing to main branch...${NC}"
    git push origin main || git push
    
    echo -e "${YELLOW}Switching back to prod branch...${NC}"
    git checkout prod
    
elif [ "$CURRENT_BRANCH" = "main" ]; then
    echo -e "${GREEN}Pushing to main branch...${NC}"
    git push origin main || git push
    
    echo -e "${YELLOW}Switching to prod branch...${NC}"
    git checkout prod
    
    echo -e "${YELLOW}Merging main into prod...${NC}"
    git merge main -m "Merge main into prod: $COMMIT_MSG"
    
    echo -e "${GREEN}Pushing to prod branch...${NC}"
    git push edge_uat prod || git push origin prod
    
    echo -e "${YELLOW}Switching back to main branch...${NC}"
    git checkout main
else
    echo -e "${RED}Error: Not on main or prod branch. Current branch: $CURRENT_BRANCH${NC}"
    echo -e "${YELLOW}Please switch to main or prod branch first${NC}"
    exit 1
fi

# Restore stashed changes
echo -e "${YELLOW}Restoring stashed changes...${NC}"
git stash pop 2>/dev/null || true

echo -e "${GREEN}✓ Successfully pushed to both main and prod branches!${NC}"
echo -e "${GREEN}Current branch: $(git branch --show-current)${NC}"

