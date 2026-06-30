# gridworks-alerts

Monitors GridWorks residential heating systems and raises alerts for potential system faults.

See [docs/alerts.md](docs/alerts.md) for alert definitions, triggers, and thresholds.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Ubuntu EC2 with systemd

## Configuration

Create `/home/ubuntu/gridworks-alerts/.env` from `.env.example`. All variables use the `GWALERT_` prefix:

| Variable | Purpose |
|----------|---------|
| `GWALERT_DB_URL` | SQLAlchemy URL for the journaldb database |
| `GWALERT_GBO_DB_URL` | SQLAlchemy URL for the backoffice database |
| `GWALERT_ALERT_MANAGER_URL` | Base URL of the alert-manager service (e.g. `http://localhost:8000`) |
| `GWALERT_ALERT_MANAGER_TOKEN` | Bearer token for `POST /new-alert` |

## EC2 setup

Install the application:

```bash
cd /home/ubuntu
git clone git@github.com:thegridelectric/gridworks-alerts.git
cd gridworks-alerts
uv sync
cp .env.example .env
# edit .env with production credentials
```

Create `/etc/systemd/system/gridworks-alerts.service`:

```ini
[Unit]
Description=GridWorks residential heating alerts
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/gridworks-alerts
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/ubuntu/gridworks-alerts/.venv/bin/gwalert
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gridworks-alerts
sudo systemctl start gridworks-alerts
```

Check status and logs:

```bash
sudo systemctl status gridworks-alerts
sudo journalctl -u gridworks-alerts -f
```

## Deploy updates

```bash
cd /home/ubuntu/gridworks-alerts
git pull
uv sync
sudo systemctl restart gridworks-alerts
```

## License

See [LICENSE](LICENSE).
