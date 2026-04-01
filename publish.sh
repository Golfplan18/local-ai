#!/bin/bash
cd ~/local-ai

echo ""
echo "Files changed since last publish:"
echo "================================="
git status --short
echo ""
echo "================================="
read -p "Commit message: " msg
if [ -z "$msg" ]; then
    echo "No commit message provided. Aborting."
    exit 1
fi
git add .
echo ""
echo "Files that will be published:"
echo "================================="
git diff --cached --name-only
echo "================================="
echo ""
read -p "Proceed? (y/n): " confirm
if [ "$confirm" = "y" ]; then
    git commit -m "$msg"
    git push
    echo "Published."
else
    git reset HEAD .
    echo "Cancelled."
fi
