#!/bin/bash
# Renew Let's Encrypt certificate (run from cron monthly)
set -e

docker run --rm \
    -v "$(pwd)/nginx/certbot/conf:/etc/letsencrypt" \
    -v "$(pwd)/nginx/certbot/www:/var/www/certbot" \
    certbot/certbot renew --quiet

# Reload nginx to pick up new cert
docker compose exec nginx nginx -s reload

echo "✅ SSL certificate renewed and nginx reloaded."
