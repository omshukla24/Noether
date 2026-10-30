#!/bin/bash
# Builds and starts Noether on an Amazon Linux 2023 instance. Safe to re-run: it is also how an update ships.
# The environment comes from the SSM parameter /noether/env, written by provision.py.
set -euxo pipefail
export HOME=/root

NODE_VERSION=24.14.0
UV_VERSION=0.9.5
CADDY_VERSION=2.10.2
APP=/opt/noether
REGION=$(TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60'); \
  curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)

if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile && mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

command -v git >/dev/null || dnf install -y git tar xz
if [ ! -x /usr/local/bin/node ] || [ "$(/usr/local/bin/node --version)" != "v$NODE_VERSION" ]; then
  curl -fsSL "https://nodejs.org/dist/v$NODE_VERSION/node-v$NODE_VERSION-linux-x64.tar.xz" | tar -xJ --strip-components=1 -C /usr/local
fi
if [ ! -x /usr/local/bin/uv ]; then
  curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi
if [ ! -x /usr/local/bin/caddy ]; then
  curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v$CADDY_VERSION/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" | tar -xz -C /usr/local/bin caddy
fi

id noether >/dev/null 2>&1 || useradd --system --create-home noether
id caddy >/dev/null 2>&1 || useradd --system --home-dir /var/lib/caddy --create-home caddy
mkdir -p /var/lib/noether && chown noether /var/lib/noether

# The checkout belongs to the service user; root re-runs this script, and git refuses that without this line.
git config --global --add safe.directory "$APP"
if [ ! -d "$APP/.git" ]; then
  git clone --depth 1 https://github.com/omshukla24/Noether.git "$APP"
else
  git -C "$APP" fetch --depth 1 origin main
  git -C "$APP" reset --hard origin/main
fi
chown -R noether "$APP"

aws ssm get-parameter --region "$REGION" --name /noether/env --with-decryption --query Parameter.Value --output text > /etc/noether.env.new
chmod 600 /etc/noether.env.new
mv /etc/noether.env.new /etc/noether.env
# Caddy only needs the host name, not the API keys.
grep '^NOETHER_HOST=' /etc/noether.env > /etc/noether-host.env
SITE_URL=$(sed -n 's/^NEXT_PUBLIC_SITE_URL=//p' /etc/noether.env)

# The build only sees the public site URL, never the API keys. It needs more heap than 2 GB of RAM allows by default.
sudo -u noether env HOME=/home/noether NEXT_TELEMETRY_DISABLED=1 NEXT_PUBLIC_SITE_URL="$SITE_URL" NODE_OPTIONS=--max-old-space-size=3072 \
  PATH=/usr/local/bin:/usr/bin:/bin bash -c "cd $APP/web && npm ci --no-audit --no-fund && npm run build"
sudo -u noether env HOME=/home/noether UV_PYTHON_INSTALL_DIR=/home/noether/python PATH=/usr/local/bin:/usr/bin:/bin \
  bash -c "cd $APP && uv venv --allow-existing --python 3.14 .venv && uv pip install --python .venv/bin/python -r web/requirements.txt"

cp "$APP"/deploy/aws/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable noether-web noether-api noether-proxy
systemctl restart noether-web noether-api noether-proxy
