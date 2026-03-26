# openvpn_tg_bot (Python)

Telegram bot for automated OpenVPN management through Docker.

The project is fully written in Python.

## Requirements

- Python `3.11+`
- Docker Engine (`docker` command must be available)
- Telegram bot token from [@BotFather](https://t.me/BotFather)

## Configuration

Create a `.env` file:

```env
ADMIN_TELEGRAM_ID=123456789
BOT_TOKEN=1231231231:AAAAAAAAABBBBCCCCCCCCCCCCCC
# Optional: path to docker if the docker command is not in PATH
# DOCKER_BIN=C:\Program Files\Docker\Docker\resources\bin\docker.exe
```

- `ADMIN_TELEGRAM_ID` - a single ID or a comma-separated list of IDs.
- `BOT_TOKEN` - Telegram bot token.
- `DOCKER_BIN` - optional full path to `docker` (useful for Linux services and Windows).

You can get your Telegram ID from [@userinfobot](https://t.me/userinfobot).

## Quick Start (Local)

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install .
ovpn-bot
```

## Running with Docker Compose

```bash
docker compose up -d --build
docker compose ps
```

`docker-compose.yml` already mounts `/var/run/docker.sock` so the bot can launch OpenVPN containers.

## Bot Commands

- `/init` - initialize OpenVPN (example: `/init tcp://0.0.0.0:443`)
- `/status` - list Docker containers and `ovpn_*` containers
- `/users` - list all users with protocol and certificate activation date
- `/generate_tcp` - generate a TCP profile (example: `/generate_tcp laptop`)
- `/generate_udp` - generate a UDP profile (example: `/generate_udp laptop`)
- `/generate` - compatibility alias, works like `/generate_tcp`
- `/remove_user` - remove a user (example: `/remove_user laptop tcp`)
- `/shutdown` - completely remove OpenVPN containers and volume
- `/help` - show command help

`/remove` is kept as a deprecated alias and redirects to `/shutdown`.

After the bot starts, the commands are available in the Telegram menu (the `/` button) and can be used without typing them manually.

### When to Use TCP vs UDP

- `TCP` - more reliable in restricted or filtered networks, usually easier to get through.
- `UDP` - usually faster and lower latency, a good choice on a normal network.

## Tests

```bash
pip install pytest
pytest
```

## Installation on a New VPS (Ubuntu)

Below is the current sequence to make sure the bot starts automatically after a server reboot.

### 1) Install Docker

```bash
sudo apt update
sudo apt install -y ca-certificates curl git

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo ${UBUNTU_CODENAME}) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

### 2) Enable Docker Autostart

```bash
sudo systemctl enable --now docker
```

### 3) Prepare the Project

```bash
cd /opt
sudo git clone <YOUR_REPOSITORY_URL> openvpn_tg_bot
cd /opt/openvpn_tg_bot
cp .env.example .env
```

Fill in `.env`:

```env
ADMIN_TELEGRAM_ID=123456789
BOT_TOKEN=1231231231:AAAAAAAAABBBBCCCCCCCCCCCCCC
# If docker is not available in PATH:
# DOCKER_BIN=/usr/bin/docker
```

### 4) Start

```bash
docker compose up -d --build
docker compose ps
```

Why the bot will start after reboot:
- `docker-compose.yml` contains `restart: unless-stopped`
- Docker is enabled through `systemctl enable docker`

### 5) Initial Telegram Setup

1. `/init tcp://<PUBLIC_IP>:443`
2. `/status`
3. `/generate_tcp laptop` or `/generate_udp laptop`
4. `/users`
