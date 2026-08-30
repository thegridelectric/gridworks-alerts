# gridworks-alerts

Monitors GridWorks residential heating systems and raises alerts for potential system faults.

See [docs/alerts.md](docs/alerts.md) for alert definitions, triggers, and thresholds.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Linux with systemd, for the service unit

## Configuration

Copy `.env.example` to `.env` (mode `600`). All variables use the `GWALERT_` prefix. The defaults are a working dev pair — a local `gridworks-data` container read as `gw_reader`, and an alert-manager on loopback with its dev token — so production values go in `.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GWALERT_DB_URL` | local dev container | SQLAlchemy URL for the JournalKeeper journal database (`tsdb`, schema `gridworks`), as a read-only role |
| `GWALERT_ALERT_MANAGER_URL` | `http://127.0.0.1:8000` | Base URL of the alert-manager service |
| `GWALERT_ALERT_MANAGER_TOKEN` | `dev-alert-token` | Bearer token for `POST /new-alert` |
| `GWALERT_SYNTHETIC_ALERT` | `false` | `true` sends one start-up alert to the alert-manager (never Opsgenie) to prove the delivery path without the database |
| `GWALERT_OPSGENIE_API_KEY` / `GWALERT_OPSGENIE_TEAM_ID` | empty | Opsgenie, the parallel fallback channel |

## Run

```bash
uv sync
uv run gwalert
```

## Service

[`service/gridworks-alerts.service`](service/gridworks-alerts.service) runs
`gwalert` from a checkout at `/home/alerts/gridworks-alerts` as the `alerts`
user, with a `MemoryMax=512M` ceiling so a runaway process can only kill the
service, never the host. Installing it needs root:

```bash
cp service/gridworks-alerts.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gridworks-alerts
```

Logs: `journalctl -u gridworks-alerts -f`. Update: `git pull && uv sync --frozen && sudo systemctl restart gridworks-alerts`.

## License

See [LICENSE](LICENSE).
