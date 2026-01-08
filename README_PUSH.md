# Push to Both Branches Script

This repository includes a script to easily push changes to both `main` and `prod` branches.

## Usage

### Method 1: Using the Script

```bash
./push_to_both.sh "Your commit message here"
```

The script will:
1. Stash any uncommitted changes (cache files, db.sqlite3)
2. Add and commit your changes (dashboard/views.py, templates/dashboard/dashboard.html)
3. Push to the current branch (prod or main)
4. Switch to the other branch
5. Merge the changes
6. Push to the other branch
7. Switch back to the original branch
8. Restore stashed changes

### Method 2: Manual Git Commands

If you're on `prod` branch:
```bash
# Commit your changes
git add dashboard/views.py templates/dashboard/dashboard.html
git commit -m "Your commit message"

# Push to prod
git push edge_uat prod

# Switch to main and merge
git checkout main
git merge prod
git push origin main

# Switch back to prod
git checkout prod
```

If you're on `main` branch:
```bash
# Commit your changes
git add dashboard/views.py templates/dashboard/dashboard.html
git commit -m "Your commit message"

# Push to main
git push origin main

# Switch to prod and merge
git checkout prod
git merge main
git push edge_uat prod

# Switch back to main
git checkout main
```

## Notes

- The script automatically handles stashing of cache files and db.sqlite3
- Make sure you're on either `main` or `prod` branch before running
- The script will push to `edge_uat` remote for prod and `origin` remote for main

