#!/usr/bin/env python3
"""
GitHub Branch Protection Setup
Configures branch protection rules to enforce CI/CD pipeline requirements.
"""

import json
import os
import sys
from typing import Dict, Any
import requests

def setup_branch_protection(
    repo_owner: str,
    repo_name: str,
    github_token: str,
    branch: str = "main"
) -> bool:
    """
    Set up branch protection rules for the repository.
    
    Args:
        repo_owner: GitHub repository owner
        repo_name: Repository name
        github_token: GitHub personal access token
        branch: Branch to protect (default: main)
    
    Returns:
        bool: True if successful, False otherwise
    """
    
    # GitHub API URL for branch protection
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/branches/{branch}/protection"
    
    # Headers for API request
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    
    # Branch protection configuration
    protection_config = {
        "required_status_checks": {
            "strict": True,  # Require branches to be up to date before merging
            "contexts": [
                # All CI/CD pipeline jobs must pass
                "🔒 Security & Code Quality",
                "🧪 Test Suite (Python 3.10)",
                "🧪 Test Suite (Python 3.11)", 
                "🧪 Test Suite (Python 3.12)",
                "🔗 Integration Tests",
                "🐳 Docker Build & Scan",
                "⚡ Performance Tests",
                "🚀 Deployment Readiness"
            ]
        },
        "enforce_admins": False,  # Allow admins to bypass restrictions
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": False,
            "require_last_push_approval": True
        },
        "restrictions": None,  # No user/team restrictions
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True
    }
    
    try:
        print(f"🔒 Setting up branch protection for {repo_owner}/{repo_name}:{branch}")
        
        # Make API request
        response = requests.put(url, headers=headers, json=protection_config)
        
        if response.status_code == 200:
            print("✅ Branch protection rules updated successfully!")
            return True
        elif response.status_code == 201:
            print("✅ Branch protection rules created successfully!")
            return True
        else:
            print(f"❌ Failed to set up branch protection: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error setting up branch protection: {e}")
        return False

def main():
    """Main function for CLI usage."""
    
    print("🔒 GitHub Branch Protection Setup")
    print("=================================")
    
    # Get configuration from environment or prompt
    repo_owner = os.getenv("GITHUB_REPO_OWNER")
    repo_name = os.getenv("GITHUB_REPO_NAME")
    github_token = os.getenv("GITHUB_TOKEN")
    
    if not repo_owner:
        repo_owner = input("Enter GitHub repository owner: ").strip()
    
    if not repo_name:
        repo_name = input("Enter repository name: ").strip()
    
    if not github_token:
        github_token = input("Enter GitHub personal access token: ").strip()
    
    if not all([repo_owner, repo_name, github_token]):
        print("❌ Missing required information")
        sys.exit(1)
    
    # Set up branch protection
    success = setup_branch_protection(repo_owner, repo_name, github_token)
    
    if success:
        print("\n🎉 Branch protection setup completed!")
        print("\n📋 Protection Rules Configured:")
        print("- ✅ All CI/CD pipeline jobs must pass")
        print("- ✅ Require 1 approving review")
        print("- ✅ Dismiss stale reviews on new commits")
        print("- ✅ Require conversation resolution")
        print("- ✅ No force pushes allowed")
        print("- ✅ No branch deletion allowed")
        print("- ✅ Branches must be up to date")
        print("\n🚀 Your main branch is now protected!")
    else:
        print("\n❌ Branch protection setup failed")
        sys.exit(1)

if __name__ == "__main__":
    main() 