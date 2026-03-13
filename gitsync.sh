#!/bin/bash

cd /srv/workspace/ASO-Service

echo "Choose action:"
echo "1) Push (Publish-to-Github)"
echo "2) Pull (Get-from-Github)"
read -p "Enter choice (1 or 2): " choice

if [ "$choice" == "1" ]; then
    echo "Checking changes..."

    if [[ -n $(git status --porcelain) ]]; then
        git add .
        git commit -m "update $(date '+%Y-%m-%d %H:%M:%S')"
        git push
        echo "✅ Project pushed to GitHub"
    else
        echo "⚠️ No changes to push"
    fi

elif [ "$choice" == "2" ]; then
    echo "Pulling latest changes from GitHub..."
    git pull origin main
    echo "✅ Project updated from GitHub"

else
    echo "❌ Invalid option"
fi
