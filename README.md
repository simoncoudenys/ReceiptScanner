# ReceiptSplitter

Upload a Colruyt receipt PDF in the browser and split the items over several people.
Python 3 (stdlib only) + `pdftotext` (poppler-utils).

## Run locally

```sh
python3 app.py   # http://localhost:8000
```

## Run in a Proxmox LXC container

### 1. Create the container (on the Proxmox host)

Via the web UI (*Create CT*) or the shell. A Debian 12 container with 1 core,
256 MB RAM and a 2 GB disk is more than enough:

```sh
pveam update
pveam download local debian-12-standard_12.7-1_amd64.tar.zst   # see `pveam available` for the exact name

pct create 120 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname receiptsplitter \
  --cores 1 --memory 256 --swap 256 \
  --rootfs local-lvm:2 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --unprivileged 1 --features nesting=1 \
  --onboot 1
pct start 120
pct enter 120
```

`nesting=1` is needed: the systemd unit uses sandboxing (`ProtectSystem`,
`PrivateTmp`, ...), which fails with `status=226/NAMESPACE` without it.

### 2. Install the app (inside the container)

```sh
apt-get update && apt-get install -y git
git clone https://github.com/simoncoudenys/ReceiptScanner.git /root/ReceiptScanner
cd /root/ReceiptScanner
./deploy/install.sh
```

The installer installs `python3` and `poppler-utils`, creates a `receiptscanner`
system user, copies the app to `/opt/receiptscanner` and starts the
`receiptscanner` systemd service on port **8000**.

Open `http://<container-ip>:8000` (find the IP with `ip -4 a show eth0`).

### Update

```sh
cd /root/ReceiptScanner && git pull && ./deploy/install.sh
```

### Manage

```sh
systemctl status receiptscanner
journalctl -u receiptscanner -f
```

Change the port with `systemctl edit receiptscanner`:

```ini
[Service]
Environment=RECEIPT_PORT=8080
```

The app has no login. Keep it on your LAN, or put it behind a reverse proxy
with authentication before exposing it to the internet.
