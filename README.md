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

Install the systemd unit from the repo (canonical copy in
[`service/gridworks-alerts.service`](service/gridworks-alerts.service) — it
includes a `MemoryMax=512M` ceiling so a runaway process can only kill the
service, never the box; see OPS-451 for the 2026-07-16 incident that taught
this):

```bash
sudo cp service/gridworks-alerts.service /etc/systemd/system/gridworks-alerts.service
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
