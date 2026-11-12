#!/usr/bin/env bash
# Run as root inside the LXC container, from the project folder:
#   sudo ./deploy/install.sh
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"

# Dependencies: python3 + pdftotext (poppler)
if command -v apt-get >/dev/null; then
  apt-get update && apt-get install -y python3 poppler-utils
elif command -v dnf >/dev/null; then
  dnf install -y python3 poppler-utils
elif command -v apk >/dev/null; then
  apk add python3 poppler-utils
fi

id receiptscanner >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin receiptscanner

install -d /opt/receiptscanner/static /var/lib/receiptscanner/in
install -m 644 "$SRC/app.py" "$SRC/colruyt_parser.py" /opt/receiptscanner/
install -m 644 "$SRC/static/index.html" /opt/receiptscanner/static/
# Seed the input folder with any PDF shipped in ./in (only if empty)
if [ -z "$(ls -A /var/lib/receiptscanner/in)" ] && ls "$SRC"/in/*.pdf >/dev/null 2>&1; then
  cp "$SRC"/in/*.pdf /var/lib/receiptscanner/in/
fi
chown -R receiptscanner:receiptscanner /var/lib/receiptscanner

install -m 644 "$SRC/deploy/receiptscanner.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now receiptscanner
systemctl --no-pager status receiptscanner | head -5
echo "Running on port 8000. Drop the receipt PDF into /var/lib/receiptscanner/in"
