#!/bin/bash
set -e

APP_DIR="/opt/super-domains"
REPO="git@github.com:wangpq-git/super-domains.git"
REGISTRY="ghcr.io"

echo "=== Super Domains Deploy ==="

# Create app directory if not exists
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Clone or pull repo (only need docker-compose.prod.yml and .env)
if [ ! -d ".git" ]; then
    git clone "$REPO" .
else
    git pull origin main
fi

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
SECRET_KEY=$(openssl rand -hex 32)
ENCRYPTION_KEY=$(openssl rand -hex 32)
DB_PASSWORD=$(openssl rand -hex 16)
EOF
    # Evaluate the commands to generate actual values
    SECRET_KEY=$(openssl rand -hex 32)
    ENCRYPTION_KEY=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)
    cat > .env << EOF
SECRET_KEY=${SECRET_KEY}
ENCRYPTION_KEY=${ENCRYPTION_KEY}
DB_PASSWORD=${DB_PASSWORD}
EOF
    echo ".env created with generated secrets"
fi

# Login to GHCR
echo "$GITHUB_TOKEN" | docker login "$REGISTRY" -u wangpq-git --password-stdin

# Pull latest images
docker compose -f docker-compose.prod.yml pull

# Deploy
docker compose -f docker-compose.prod.yml up -d

echo "=== Deploy complete ==="
echo "Service running on port 8080"
docker compose -f docker-compose.prod.yml ps
