# systemd Operation

The service should run as a dedicated local user and keep the watcher running:

```bash
sudo useradd --system --home /opt/health-pdf-importer --shell /usr/sbin/nologin health-pdf-importer
sudo mkdir -p /opt/health-pdf-importer /etc/health-pdf-importer /data/health-import/{inbox,processing,done,review,error,archive}
sudo chown -R health-pdf-importer:health-pdf-importer /opt/health-pdf-importer /data/health-import
sudo install -m 0644 deploy/systemd/health-pdf-importer.env /etc/default/health-pdf-importer
sudo install -m 0644 deploy/systemd/health-pdf-importer.service /etc/systemd/system/health-pdf-importer.service
sudo systemctl daemon-reload
sudo systemctl enable --now health-pdf-importer.service
```

Create `/etc/health-pdf-importer/app.yaml` from `config/app.example.yaml`. If
you use the provided unit unchanged, configure folders below
`/data/health-import/...`.

Check service status and logs:

```bash
systemctl status health-pdf-importer.service
journalctl -u health-pdf-importer.service -f
```

The unit uses `Restart=on-failure`, writes logs to journald, and reads runtime
options from `/etc/default/health-pdf-importer`.
