#!/usr/bin/env python3
"""
Script to push changes to both main and prod branches
Usage: python3 push_to_both.py "Your commit message"
"""

import subprocess
import sys
import os

def run_command(cmd, check=True):
    """Run a shell command and return the output"""
    try:
        result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        return result.stdout.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error: {e.stderr}")
        return None, e.returncode

def get_current_branch():
    """Get the current git branch"""
    output, _ = run_command("git branch --show-current", check=False)
    return output

def main():
    if len(sys.argv) < 2:
        print("Error: Commit message is required")
        print("Usage: python3 push_to_both.py \"Your commit message\"")
        sys.exit(1)
    
    commit_msg = sys.argv[1]
    current_branch = get_current_branch()
    
    print(f"Current branch: {current_branch}")
    
    if current_branch not in ['main', 'prod']:
        print(f"Error: Not on main or prod branch. Current branch: {current_branch}")
        print("Please switch to main or prod branch first")
        sys.exit(1)
    
    # Stash uncommitted changes
    print("Stashing uncommitted changes...")
    run_command("git stash push -m 'Auto-stash before push_to_both'", check=False)
    
    # Add changes
    print("Adding changes...")
    run_command("git add dashboard/views.py templates/dashboard/dashboard.html", check=False)
    
    # Check if there are changes to commit
    _, returncode = run_command("git diff --staged --quiet", check=False)
    if returncode != 0:
        print("Committing changes...")
        run_command(f'git commit -m "{commit_msg}"')
    else:
        print("No changes to commit")
    
    if current_branch == 'prod':
        # Push to prod
        print("Pushing to prod branch...")
        run_command("git push edge_uat prod", check=False) or run_command("git push origin prod", check=False)
        
        # Switch to main
        print("Switching to main branch...")
        run_command("git checkout main")
        
        # Apply changes directly to main (not merge)
        print("Applying changes to main branch...")
        run_command("git checkout prod -- dashboard/views.py templates/dashboard/dashboard.html", check=False)
        run_command("git add dashboard/views.py templates/dashboard/dashboard.html", check=False)
        
        # Check if there are changes to commit
        _, returncode = run_command("git diff --staged --quiet", check=False)
        if returncode != 0:
            run_command(f'git commit -m "{commit_msg}"')
        else:
            print("No new changes to commit in main")
        
        # Push to main
        print("Pushing to main branch...")
        run_command("git push origin main", check=False) or run_command("git push", check=False)
        
        # Switch back to prod
        print("Switching back to prod branch...")
        run_command("git checkout prod")
        
    elif current_branch == 'main':
        # Push to main
        print("Pushing to main branch...")
        run_command("git push origin main", check=False) or run_command("git push", check=False)
        
        # Switch to prod
        print("Switching to prod branch...")
        run_command("git checkout prod")
        
        # Apply changes directly to prod (not merge)
        print("Applying changes to prod branch...")
        run_command("git checkout main -- dashboard/views.py templates/dashboard/dashboard.html", check=False)
        run_command("git add dashboard/views.py templates/dashboard/dashboard.html", check=False)
        
        # Check if there are changes to commit
        _, returncode = run_command("git diff --staged --quiet", check=False)
        if returncode != 0:
            run_command(f'git commit -m "{commit_msg}"')
        else:
            print("No new changes to commit in prod")
        
        # Push to prod
        print("Pushing to prod branch...")
        run_command("git push edge_uat prod", check=False) or run_command("git push origin prod", check=False)
        
        # Switch back to main
        print("Switching back to main branch...")
        run_command("git checkout main")
    
    # Restore stashed changes
    print("Restoring stashed changes...")
    run_command("git stash pop", check=False)
    
    print(f"✓ Successfully pushed to both main and prod branches!")
    print(f"Current branch: {get_current_branch()}")

if __name__ == "__main__":
    main()

