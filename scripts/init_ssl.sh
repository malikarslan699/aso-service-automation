#!/bin/bash
# ============================================================
# init_ssl.sh — Get Let's Encrypt SSL cert for aso.zouqly.com
# Run ONCE on first deployment, before starting nginx properly.
# ============================================================

set -e

DOMAIN="aso.zouqly.com"
EMAIL="${SSL_EMAIL:-admin@zouqly.com}"   # Set SSL_EMAIL env var to override

CERT_DIR="./nginx/certbot/conf/live/$DOMAIN"
WWW_DIR="./nginx/certbot/www"

mkdir -p "$WWW_DIR" ./nginx/certbot/conf

# Check if cert already exists
if [ -d "$CERT_DIR" ]; then
    echo "✅ Certificate already exists at $CERT_DIR — skipping."
    echo "   To renew: make ssl-renew"
    exit 0
fi

echo "🔐 Obtaining Let's Encrypt certificate for $DOMAIN ..."

# Start a temporary nginx on port 80 for ACME challenge
# (only if nginx is not already running)
if ! docker compose ps nginx | grep -q "Up"; then
    # Use a minimal nginx config that only serves the ACME challenge
    cat > /tmp/nginx_acme.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'ok'; add_header Content-Type text/plain; }
}
EOF
    docker run --rm -d \
        --name nginx_acme_temp \
        -p 80:80 \
        -v /tmp/nginx_acme.conf:/etc/nginx/conf.d/default.conf:ro \
        -v "$(pwd)/nginx/certbot/www:/var/www/certbot:ro" \
        nginx:alpine

    TEMP_NGINX_STARTED=true
fi

# Run certbot
docker run --rm \
    -v "$(pwd)/nginx/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/nginx/certbot/www:/var/www/certbot" \
    certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"

# Stop temp nginx if we started it
if [ "$TEMP_NGINX_STARTED" = "true" ]; then
    docker stop nginx_acme_temp 2>/dev/null || true
fi

echo ""
echo "✅ Certificate obtained successfully!"
echo "   Now run: make deploy"
