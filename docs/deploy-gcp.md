# Deploying POLAR WINDOW on Google Cloud

Target: `https://polarwindow.ahbab.tech` on one Compute Engine VM: `spaceapps`, project
`ahbab-512109`, zone `us-central1-c`, e2-small (2 vCPU, 2 GB) with a 20 GB SSD (grown from 15 GB
on 13 November, live: `gcloud compute disks resize`, then `growpart /dev/sda 1` and
`resize2fs /dev/sda1`), Ubuntu 26.10,
address 35.225.159.7. From the PC, `ssh ahbabssh` reaches it (an entry in `~/.ssh/config`
using the key `gcloud compute ssh` registered). Written 13 November 2026.
Every size and time below was measured on the owner's PC on 13 November unless it says
otherwise. The files this runbook uses are in `deploy/`.

## Summary

1. The app runs with `docker compose` (postgres, redis, api, compute, feeds, web), as in the repository.
2. Every container port is published on 127.0.0.1 only. nginx on the host is the only thing open to the internet.
3. Host nginx holds a Let's Encrypt certificate and sends `/api/` and `/healthz` to the api (port 8000) and the rest to the web container (port 8080).
4. The dashboard asks `/api/v1` on its own origin, so there is no CORS and no `localhost` in the build.
5. The results worked out on the PC travel as a `pg_dump` (60 MB) and the data as two tar files (1.3 GB and 1.5 GB).
6. Before the first start, git checks out the catalogue files with Windows line endings so their hashes match the stored answers (B1).
7. The database is restored before the app first starts, so nothing is worked out again.
8. Settings for a public site come from `deploy/env.production.example`; the owner types the two API keys.
9. Docker restarts everything after a reboot; a timer backs the database up daily and another checks health every 5 minutes.
10. Machine: e2-small (2 GB) with 4 GB of swap and a 15 GB disk, the owner's choice. The
    disk is tight: the data streams over SSH straight into place (no tar files on the VM),
    and build cache is pruned after the build. e2-standard-2 with 40 GB was the first advice.

## Rules for whoever runs this

- Each step says **On the PC** or **On the VM**. The VM steps assume the repository at `/opt/polarwindow`.
- **ASK THE OWNER FIRST** marks every step that touches DNS, a firewall rule or a database. Stop there and wait for a yes.
- Never print, paste or copy `.env` once it holds secrets. Do not run `cat .env` or a bare `docker compose config` (it prints every setting). Never ask the owner to paste a key into the chat: the owner types keys into `.env` in their own terminal.
- Never run `docker compose down -v`, `docker volume rm` or `python3 run_onVM.py --fresh-db` on the VM unless a rollback step below says so and the owner agreed. They delete the database.
- Run every stage's **Check**. Do not go on when a check fails; use that stage's **Rollback** or ask the owner.
- `sudo` is needed for Docker and nginx. Run git as the normal SSH user.

## Pre-flight checklist

The owner does or confirms these before stage 2. Each one is **ASK THE OWNER FIRST**.

- [x] A VM exists: `spaceapps`, e2-small, Ubuntu 26.10 x86_64, us-central1-c, 15 GB disk.
- [x] Its external address 35.225.159.7 is reserved as the static address `polarwindow`
  (us-central1, 13 November: `gcloud compute addresses create polarwindow --addresses
  35.225.159.7 --region us-central1 --project ahbab-512109`), so a stop and start keeps it.
- [ ] DNS: an A record `polarwindow.ahbab.tech` points at that static IP. (Checked on the VM in stage 9.)
- [ ] Firewall: TCP 80 and 443 are open to the VM from anywhere (on the VM page, "Allow HTTP traffic" and "Allow HTTPS traffic", which use the default `default-allow-http` and `default-allow-https` rules). Port 80 must stay open: certificate renewals use it.
- [ ] SSH to the VM works.
- [ ] The repository clones: `git clone https://github.com/MdAhbab/PolarWindow.git`. If it asks for a password the repository is private; the owner supplies a read-only GitHub token.
- [ ] The owner has an api.nasa.gov key (free) and the Gemini key at hand, to type into `.env` in stage 5.
- [ ] Stage 0 and stage 1 are done: `~/pw-deploy/` on the VM holds the bundle.

Quick look at the machine (On the VM):

```bash
lsb_release -ds; uname -m; nproc; free -g | head -2; df -h /
# Ubuntu 24.04.x LTS, x86_64, 2, about 8 GB total, about 40 GB disk
```

## Stage 0. Make the bundle (On the PC)

When: after the last code commit is pushed, when the PC's app has finished working out its
answers (no job queued or running), and not while a demo is being recorded. The script reads
only; it took 49 s without the 5 m terrain on 13 November.

```powershell
cd "C:\Users\ahbab\Downloads\Nasa Spaceapps\polarwindow"
git status --short          # app code and data/catalogues committed and pushed
powershell -ExecutionPolicy Bypass -File deploy\pc-export.ps1
```

It writes `%USERPROFILE%\pw-deploy\`:

| File | What | Size on 13 Nov |
|---|---|---|
| `polar_window.dump` | `pg_dump -Fc` of the local database | 60 MB |
| `pw-data-core.tar` | 4,693 data files the running app reads | 1.27 GB |
| `pw-data-lola5m.tar` | 27 tiles of 5 m terrain (landing ellipse) | 1.54 GB |
| `catalogues.sha256` | sha256 of `data/catalogues/*.json` on this PC | small |
| `pc-info.txt` | commit, migration, row counts | small |
| `SHA256SUMS` | sha256 of all of the above | small |

`-NoLola` leaves out the 1.5 GB terrain tar. The app then falls back to its own 20 m terrain for
the landing ellipse and says so on the page.

**Check.** The script ends with the file table and `pc-info.txt`. It stops by itself if a job is
still running. A warning about uncommitted or unpushed changes means: commit and push, then run it
again.

**Rollback.** Nothing on the PC changed. Delete `%USERPROFILE%\pw-deploy` to start again.

## Stage 1. Copy the bundle to the VM (On the PC)

With the Google Cloud CLI on the PC (replace `VM_NAME` and `ZONE`):

```powershell
gcloud compute ssh VM_NAME --zone ZONE --command "mkdir -p ~/pw-deploy"
gcloud compute scp --zone ZONE "$HOME\pw-deploy\*" VM_NAME:~/pw-deploy/
```

On the 15 GB disk, copy only the small files and stream the two tars straight into place
after stage 2, so they never sit on the VM's disk (this replaces the `tar -xf` lines of stage 4):

```bash
# On the PC (Git Bash), after stage 2 made /opt/polarwindow:
cd ~/pw-deploy
ssh ahbabssh 'mkdir -p ~/pw-deploy'
scp polar_window.dump catalogues.sha256 pc-info.txt SHA256SUMS *.list ahbabssh:pw-deploy/
ssh ahbabssh 'cd /opt/polarwindow && tar -x' < pw-data-core.tar
ssh ahbabssh 'cd /opt/polarwindow && tar -x' < pw-data-lola5m.tar     # only if the disk has room
```

Check the tars on the PC instead (`sha256sum -c SHA256SUMS` there); stage 4's file-list check
then confirms every file arrived.

If the upload breaks part-way, a bucket is resumable on both sides:

```powershell
gcloud storage buckets create gs://BUCKET --location=asia-south1     # ASK THE OWNER FIRST (a new resource)
gcloud storage cp "$HOME\pw-deploy\*" gs://BUCKET/pw-deploy/
```

and then On the VM: `mkdir -p ~/pw-deploy && gcloud storage cp 'gs://BUCKET/pw-deploy/*' ~/pw-deploy/`
(the VM's default access includes reading Cloud Storage).

**Check (On the VM).**

```bash
cd ~/pw-deploy && sha256sum -c SHA256SUMS      # every line "OK"
```

If `~/pw-deploy` is missing, the copy went to another user's home (the PC's gcloud user name can
differ from the SSH user here): `ls -d /home/*/pw-deploy`, then
`sudo mv /home/OTHER/pw-deploy ~/ && sudo chown -R "$USER": ~/pw-deploy`.

**Rollback.** `rm -rf ~/pw-deploy` and copy again.

## Stage 2. Packages and the code (On the VM)

```bash
sudo apt-get update && sudo apt-get install -y git
sudo mkdir -p /opt/polarwindow && sudo chown "$USER": /opt/polarwindow
git clone https://github.com/MdAhbab/PolarWindow.git /opt/polarwindow
cd /opt/polarwindow
sudo bash deploy/vm-setup.sh
```

`deploy/vm-setup.sh` installs Docker with the compose plugin, nginx, certbot, jq and dig; caps
each container's log at 5 files of 10 MB; adds a 2 GB swap file; makes `/var/www/certbot` and
`/var/backups/polarwindow`. It opens no port and starts nothing of the app.

**Check.**

```bash
git -C /opt/polarwindow rev-parse HEAD
grep '^commit=' ~/pw-deploy/pc-info.txt        # the same commit
sudo docker compose version                    # 2.24 or newer
cat /etc/docker/daemon.json                    # max-size 10m, max-file 5
```

If the two commits differ, see what changed in the inputs the stored answers depend on
(replace `PC_COMMIT`):

```bash
git diff --stat PC_COMMIT HEAD -- data/catalogues data/missions.json backend/app/config.py backend/alembic
```

Empty: go on. Not empty: ASK THE OWNER whether to deploy the PC's commit instead
(`git checkout -B deploy PC_COMMIT`).

**Rollback.** `sudo rm -rf /opt/polarwindow` and clone again. The packages can stay.

## Stage 3. Catalogue line endings, before anything starts (On the VM)

Why: a stored answer is found by a key that includes the sha256 of the catalogue files' bytes
(`backend/app/data/catalogues.py:470`, used at `trip_service.py:125-127`,
`contact_service.py:235-236`, `launch_service.py:245-246`, `scenario_service.py:601-604`). The PC
checks 9 of the 10 files out with Windows line endings (`git ls-files --eol data/catalogues`:
`i/lf w/crlf`); `lander_examples.json` is LF there. A Linux clone gets LF everywhere, so every
stored trip, contact, launch and scenario answer would be missed and worked out again. These
lines make this clone write the same bytes as the PC. `.git/info/attributes` belongs to this clone
only and is never committed.

```bash
cd /opt/polarwindow
printf '%s\n' 'data/catalogues/*.json text eol=crlf' \
              'data/catalogues/lander_examples.json text eol=lf' >> .git/info/attributes
rm data/catalogues/*.json
git checkout -- data/catalogues
```

**Check.**

```bash
sha256sum -c ~/pw-deploy/catalogues.sha256     # 10 lines "OK"
git status --short                             # prints nothing
```

On 13 November `ground_stations.json` began `edc6766d5965b967` on the PC and `e6563ebf5841ee9a`
with LF.

**Rollback.** `sed -i '/data\/catalogues/d' .git/info/attributes && rm data/catalogues/*.json && git checkout -- data/catalogues`

## Stage 4. The data (On the VM)

Extract as the normal user, not with sudo, so no file is world-writable.

```bash
cd /opt/polarwindow
tar -xf ~/pw-deploy/pw-data-core.tar
[ -f ~/pw-deploy/pw-data-lola5m.tar ] && tar -xf ~/pw-deploy/pw-data-lola5m.tar
```

**Check.**

```bash
cat ~/pw-deploy/pw-data-core.list ~/pw-deploy/pw-data-lola5m.list | while read -r f; do [ -f "$f" ] || echo "missing $f"; done
# prints nothing (lola5m lines are "missing" only if that tar was left out on purpose)
du -sh data                                    # about 2.7 GB with the 5 m terrain
```

**Rollback.** Extracting only adds files. Extract again to repair.

## Stage 5. Settings (On the VM)

```bash
cd /opt/polarwindow
cp deploy/env.production.example .env
chmod 600 .env
sed -i "s/^PW_JWT_SECRET=.*/PW_JWT_SECRET=$(openssl rand -hex 48)/" .env
sed -i "s/^PW_DB_PASSWORD=.*/PW_DB_PASSWORD=$(openssl rand -hex 24)/" .env
```

The two `sed` lines write new secrets without printing them.

**ASK THE OWNER** to open `.env` in their own terminal (`nano /opt/polarwindow/.env`) and replace
`CHANGE_ME_GEMINI_API_KEY` and `CHANGE_ME_NASA_API_KEY` with the keys (or `DEMO_KEY` for NASA if
there is none). If the PC's `.env` has a model order that is known to work, the owner may copy its
two `PW_AGENT_MODELS` lines over too.

**Check** (prints no secret):

```bash
grep -nE '^[^#]*CHANGE_ME' .env                # prints nothing (comments may mention it)
grep -cE '^PW_(JWT_SECRET|DB_PASSWORD)=[0-9a-f]{48,}$' .env     # 2
sudo docker compose config --format json \
  | jq -r '.services | to_entries[] | select(.value.ports) | .key + " " + (.value.ports | map((.host_ip // "ALL") + ":" + (.published|tostring) + "->" + (.target|tostring)) | join(","))'
# api 127.0.0.1:8000->8000, postgres 127.0.0.1:5432->5432, redis 127.0.0.1:6379->6379, web 127.0.0.1:8080->80
```

**Rollback.** `cp deploy/env.production.example .env` and repeat. Before stage 7 the database
password can still change; after it, `PW_DB_PASSWORD` must stay as it is (it is used only when the
database volume is first made).

## Stage 6. Build the images (On the VM)

```bash
cd /opt/polarwindow
sudo docker compose build --pull api web
```

The backend image installs the Python packages from `backend/uv.lock`; the web image runs
`npm ci` and `npm run build` with `VITE_API_BASE=/api/v1` (`docker-compose.yml:157`,
`frontend/Dockerfile:15-17`). Build time on the VM was not measured (no Docker on the PC).

**Check.** `sudo docker images | grep polar-window` lists `polar-window-backend` and `polar-window-web`.

**Rollback.** `sudo docker image rm polar-window-backend polar-window-web` and build again.

## Stage 7. Restore the database (On the VM): ASK THE OWNER FIRST

This creates the database volume `polar-window_pgdata` and fills it from the PC's dump. Do it
before the app's first start, so the app finds every stored answer at once.

```bash
cd /opt/polarwindow
sudo docker compose up -d postgres redis
sudo docker compose exec -T postgres pg_isready -U postgres -d polar_window
sudo docker compose exec -T postgres psql -U postgres -d polar_window -Atc \
  "select count(*) from pg_tables where schemaname='public'"      # 0: a new, empty database
sudo docker compose exec -T postgres pg_restore -U postgres -d polar_window \
  --no-owner --no-privileges --single-transaction --exit-on-error < ~/pw-deploy/polar_window.dump
```

`--single-transaction --exit-on-error`: on any error nothing is kept, so it can simply be run
again. The same command restored a fresh dump into a scratch PostgreSQL 16.11 in 4.7 s on
13 November, with every count equal.

**Check.**

```bash
q() { sudo docker compose exec -T postgres psql -U postgres -d polar_window -Atc "$1"; }
q "select version_num from alembic_version"
q "select 'missions='||(select count(*) from missions), 'sites='||(select count(*) from sites),
          'assessments='||(select count(*) from assessments), 'jobs='||(select count(*) from jobs),
          'scenarios='||(select count(*) from scenarios), 'users='||(select count(*) from users)"
grep -E '^(alembic|missions|sites|assessments|jobs|scenarios|users)=' ~/pw-deploy/pc-info.txt
# the migration and every count equal (13 Nov: a7c9e1b3d5f8, 22, 22, 187, 188, 65, 13)
```

**Rollback** (ASK THE OWNER FIRST, it deletes the database):
`sudo docker compose down && sudo docker volume rm polar-window_pgdata`, then this stage again.

## Stage 8. First start and the checks on this machine (On the VM)

```bash
cd /opt/polarwindow
sudo bash deploy/vm-up.sh --no-build
```

`deploy/vm-up.sh` checks `.env`, stamps the commit into it (`PW_CODE_VERSION`), gives `data/`
to the containers' user (uid 10001), runs `docker compose up -d`, waits for `migrate` (no-op:
the database is at the head) and `data` (a check: everything is on disk), and waits for
`/healthz`. Nothing is reachable from outside yet: every port is on 127.0.0.1.

**Check.**

```bash
sudo bash deploy/vm-check.sh
```

It must end `ALL PASS`. What it checks:

1. ports 5432, 6379, 8000 and 8080 listen on 127.0.0.1 only;
2. all six services run;
3. `/healthz` answers `ok` (or `degraded` for a few minutes while the feeds worker fetches) and the dashboard answers on 127.0.0.1:8080;
4. the catalogue hashes on disk equal the keys of the stored trip answers (B1);
5. a stored answer is served with no new job: `GET /api/v1/missions/im-1/trip` gives 200 with `data.source` `flown`, and `select count(*) from jobs where kind='trip'` is the same before and after (202 and one more job would mean the key missed);
6. no built file names `localhost:8000` and the bundle's API base is `"/api/v1"`;
7. at most 10 jobs queued.

The same check by hand:

```bash
q() { sudo docker compose exec -T postgres psql -U postgres -d polar_window -Atc "$1"; }
q "select count(*) from jobs where kind='trip'"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/v1/missions/im-1/trip    # 200
q "select count(*) from jobs where kind='trip'"                                              # unchanged
q "select kind, status, count(*) from jobs where id > $(grep '^jobs_max_id=' ~/pw-deploy/pc-info.txt | cut -d= -f2) group by 1,2"
```

Expected new jobs after the first start: up to three `scenario` jobs. The PC re-ran the same
three presets of mission `im-3` at every API start (18 to 19 runs each in its `jobs` table;
19 s, 19 s and 5 s on average). Dozens of new scenario jobs mean the keys missed: stop, and
check stage 3.

**Rollback.** `sudo docker compose down` stops everything and keeps the database and `data/`.
Fix, then `sudo bash deploy/vm-up.sh --no-build` again.

## Stage 9. nginx and the certificate (On the VM): ASK THE OWNER FIRST

Needs the DNS record and ports 80 and 443 open (pre-flight). A `.dev` name works only over
HTTPS, so the site goes live only when the certificate exists.

DNS:

```bash
dig +short polarwindow.ahbab.tech @8.8.8.8
curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip; echo
# the same address twice
```

A port-80 site that only serves the certificate challenge:

```bash
cd /opt/polarwindow
sudo rm -f /etc/nginx/sites-enabled/default
sudo cp deploy/nginx/acme-bootstrap.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/acme-bootstrap.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo mkdir -p /var/www/certbot/.well-known/acme-challenge
echo ok | sudo tee /var/www/certbot/.well-known/acme-challenge/pw-test >/dev/null
```

Ask the owner to run, from the PC, `curl.exe http://polarwindow.ahbab.tech/.well-known/acme-challenge/pw-test`
It must print `ok`. Then:

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d polarwindow.ahbab.tech \
  --dry-run --agree-tos --register-unsafely-without-email          # the staging server: no rate limit
sudo certbot certonly --webroot -w /var/www/certbot -d polarwindow.ahbab.tech \
  --agree-tos --no-eff-email -m OWNER_EMAIL                        # ask the owner for the address
sudo install -d /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' | sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh >/dev/null
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
sudo rm -f /var/www/certbot/.well-known/acme-challenge/pw-test
```

(If the owner gives no address, use `--register-unsafely-without-email` in the second command too.)

The real site:

```bash
sudo cp deploy/nginx/polarwindow.ahbab.tech.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/polarwindow.ahbab.tech.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/acme-bootstrap.conf
sudo nginx -t && sudo systemctl reload nginx
```

**Check.**

```bash
sudo bash deploy/vm-check.sh --site      # ALL PASS: https 200 on /, /healthz, /api/v1/missions; http 301; HSTS; certificate dates
sudo certbot renew --dry-run             # "Congratulations, all simulated renewals succeeded"
systemctl list-timers certbot.timer      # the renewal timer is scheduled
```

If only the `--site` lines fail and everything works from the PC (`curl.exe -I https://polarwindow.ahbab.tech/`),
the VM cannot reach its own public address; that is not a fault of the site.

Then the owner opens `https://polarwindow.ahbab.tech` in a browser: the front page's films play,
"Open the dashboard" signs in, a flown mission's Trip shows at once, and Ask answers.

**Rollback.** Take the site down, keep the certificate:

```bash
sudo rm -f /etc/nginx/sites-enabled/polarwindow.ahbab.tech.conf
sudo ln -sf /etc/nginx/sites-available/acme-bootstrap.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## Stage 10. Staying up (On the VM)

```bash
cd /opt/polarwindow
sudo cp deploy/systemd/polarwindow-*.service deploy/systemd/polarwindow-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now polarwindow-backup.timer polarwindow-health.timer
sudo systemctl start polarwindow-backup.service             # a first backup now
sudo cp ~/pw-deploy/polar_window.dump /var/backups/polarwindow/pc-day0-polar_window.dump
rm ~/pw-deploy/pw-data-*.tar                                # 2.8 GB back; the data is in place
```

**Check.**

```bash
ls -lh /var/backups/polarwindow                             # one polar_window-<time>.dump and the day-0 copy
systemctl list-timers 'polarwindow-*' certbot.timer
journalctl -u polarwindow-backup --since today | tail -3
```

Reboot test, **ASK THE OWNER FIRST** (the site is off for a minute or two):
`sudo reboot`, reconnect, then `sudo bash deploy/vm-check.sh --site`. Docker brings back every
service with `restart: unless-stopped` (postgres and redis included, `docker-compose.yml:66`,
`:78`); `migrate` and `data` do not run again.

**Rollback.** `sudo systemctl disable --now polarwindow-backup.timer polarwindow-health.timer`.

## Updating later (On the VM)

```bash
cd /opt/polarwindow
sudo bash deploy/backup.sh                   # a fresh backup first
git rev-parse HEAD > ~/pw-last-good-commit
git pull --ff-only
sha256sum -c ~/pw-deploy/catalogues.sha256   # see below if this fails
sudo bash deploy/vm-up.sh                    # build, migrate (alembic upgrade head), data check, restart what changed
sudo bash deploy/vm-check.sh --site
```

- The database and `data/` stay: `vm-up.sh` never removes a volume. The `migrate` step runs
  `alembic upgrade head`; upgrades add and drop nothing (`docs/runbook.md` section 4).
- If a catalogue file changed upstream, the sha256 check and check 4 of `vm-check.sh` fail, as
  they should: stored answers that use that catalogue are worked out again as they are asked
  for. A full re-run of the presets took 45 jobs and 2,474 s of compute on the PC on 13 November.
- If `deploy/nginx/*.conf` or `deploy/systemd/*` changed, copy them again as in stages 9 and 10.
- Old images and build cache: `sudo docker image prune -f && sudo docker builder prune -f --filter until=168h`.

**Rollback.**

```bash
cd /opt/polarwindow
git checkout "$(cat ~/pw-last-good-commit)"
sudo bash deploy/vm-up.sh
```

The schema is additive, so the older code runs on the newer database (`docs/runbook.md`
section 6). If it does not, restore the backup taken before the update (next section). Return to
the branch later with `git checkout main`.

`python3 run_onVM.py` also works on this VM: it reads `PW_WEB_PORT` (8080) from `.env` and uses
the same project name, but it rebuilds without cache and prunes every time, so it is slower.

## Restore a backup (On the VM): ASK THE OWNER FIRST

```bash
cd /opt/polarwindow
ls -lh /var/backups/polarwindow
sudo docker compose stop api compute feeds web
sudo docker compose exec -T postgres dropdb -U postgres --force polar_window
sudo docker compose exec -T postgres createdb -U postgres polar_window
sudo docker compose exec -T postgres pg_restore -U postgres -d polar_window \
  --no-owner --no-privileges --single-transaction --exit-on-error < /var/backups/polarwindow/polar_window-TIME.dump
sudo bash deploy/vm-up.sh --no-build
sudo bash deploy/vm-check.sh --site
```

## Day to day (On the VM)

| Want | Command |
|---|---|
| Status | `cd /opt/polarwindow && sudo docker compose ps` and `curl -s localhost:8000/healthz \| jq .status` |
| Logs | `sudo docker compose logs --tail 100 api` (or `compute`, `feeds`, `web`); nginx: `/var/log/nginx/` |
| Health history | `journalctl -t polarwindow-health --since today` |
| Disk | `df -h /`, `sudo docker system df`, `sudo du -sh /var/backups/polarwindow` |
| Database size | `sudo docker compose exec -T postgres psql -U postgres -d polar_window -Atc "select pg_size_pretty(pg_database_size('polar_window'))"` |
| AI spending too much | Settings, AI assistant, Off; or blank `PW_GEMINI_API_KEY` in `.env` and `sudo docker compose up -d api` |
| A second compute worker (4 vCPUs) | `sudo docker compose up -d --scale compute=2` |

## Why: the decisions, with proof

### 1. Docker compose behind nginx on the host

- The compose file already runs every part in the right order: `migrate`, then `data`, then
  api, compute and feeds (`docker-compose.yml` `x-ready` and `depends_on`), with health checks and
  restart policies. Plain systemd units would need Python 3.12 with uv, Node 24, PostgreSQL 16 and
  Redis set up by hand on the host: more to get wrong, more to keep up for ten weeks.
- `run_onVM.py` as it was cannot be the front: it serves the dashboard on port 80 over plain HTTP
  (`run_onVM.py:409`, `docker-compose.yml:159`), and the old runbook says HTTPS needs a TLS proxy in
  front. It also rebuilds without cache and prunes on every run (`run_onVM.py:389-396`, `:433`) and
  has no database restore. It stays usable as a fallback (see "Updating later").
- The web container proxies `/api/` itself (`frontend/nginx.conf:18-28`) and sets
  `X-Forwarded-For $remote_addr`. Behind the host's nginx that address would be the Docker gateway
  for every visitor, and the api's limits are counted per address (`backend/app/api/limits.py:199-200`),
  so all visitors would share one allowance. So the host's nginx sends `/api/` and `/healthz`
  straight to the api on 127.0.0.1:8000 with the visitor's address, and the api believes it because
  `PW_FORWARDED_ALLOW_IPS=*` (`docker-compose.yml:123`; uvicorn 0.34 takes the first address when it
  trusts every peer, `uvicorn/middleware/proxy_headers.py:132-133`). Port 8000 is reachable from the
  VM only.
- The web container never takes port 80 or 443: `PW_WEB_ADDR=127.0.0.1`, `PW_WEB_PORT=8080`.

### 2. How the dashboard reaches the api

- Build argument `VITE_API_BASE=/api/v1` (`docker-compose.yml:157`, default also `/api/v1` in
  `frontend/Dockerfile:15-16`). The code falls back to `http://localhost:8000/api/v1` only when the
  variable is unset (`frontend/src/lib/api/client.ts:71-72`, `frontend/src/lib/session.ts:90`).
- Measured on 13 November: a `vite build` with that value has `const Ka="/api/v1"` and no
  `localhost:8000` in any `assets/*.js`. Two `http://localhost` strings are react-router's base for
  parsing URLs, not an API address. `snapshot/index.json` records `"api_base": "http://localhost:8000/api/v1"`
  as metadata; nothing reads it (`frontend/src/lib/api/snapshot.ts:29`). `vm-check.sh` check 6 repeats
  this on the VM.

### 3. CORS, host names, upload size, long requests

- CORS: pages and api share one origin, so the browser sends no CORS request. `PW_CORS_ORIGINS` is
  set to `https://polarwindow.ahbab.tech` only; the default lists only localhost
  (`backend/app/config.py:115-122`, used at `backend/app/main.py:211-218`).
- Host names: the app has no allowed-hosts check (`main.py` adds none). nginx answers only
  `polarwindow.ahbab.tech`; any other name gets no answer on 80 (`return 444`) and a refused TLS
  handshake on 443 (`ssl_reject_handshake on`).
- Upload: the intake file may be 8 MB (`config.py:233`, `PW_MAX_UPLOAD_BYTES`, applied only to
  `/projects/intake` at `main.py:187-191`); every other body stops at 64 KB (`config.py:230`).
  nginx's own default is 1 MB, so `/api/` gets `client_max_body_size 9m`: up to 9 MB reaches the
  api, which answers past 8 MB in its own words. The same fix went into `frontend/nginx.conf`.
- Timeouts: `proxy_read_timeout 120s` on `/api/`. The longest request is reading a project file,
  which gives the model up to 70 s in all (`backend/app/agents/intake.py:83`). Ask stops at 20 s
  (`config.py:294`). Trip, contact, launch and scenario answers are jobs: the request returns at once
  with a job to poll (`backend/app/services/job_service.py:142-187`). Nothing streams: no
  `StreamingResponse`, server-sent events or WebSocket in `backend/app/api` or `frontend/src`.

### 4. Settings for a public site (`deploy/env.production.example`)

| Setting | Value | Why |
|---|---|---|
| `PW_ENV` | `prod` | Refuses to start without `PW_JWT_SECRET` (`config.py:330-337`) |
| `PW_JWT_SECRET` | 96 hex, made on the VM | Sessions survive restarts (`config.py:216-220`) |
| `PW_DB_PASSWORD` | 48 hex, made on the VM | Compose sets the database URL itself (`docker-compose.yml:37`), so a password in `PW_DATABASE_URL` would be ignored; this variable feeds both the URL and `POSTGRES_PASSWORD` (`:61`) |
| `PW_CORS_ORIGINS` | the site's origin | See 3 |
| `PW_GEMINI_API_KEY` | the owner's key | Blank runs every AI panel from measurements (`config.py:304-311`) |
| `PW_AGENT_MODELS` | 3.6-flash, 3.5-flash, 3.5-flash-lite first | `docs/handoff.md` section 3: these answer in 3 to 5 s; 3.8 and 3.7 stay silent and each cost an 8 s attempt (`config.py:296`) |
| `PW_NASA_API_KEY` | the owner's key | `DEMO_KEY` allows 30 requests an hour (`config.py:254-256`) |
| `PW_DEMO_SIGN_IN` | `true` | The judges' one-click sign-in (`config.py:221-225`) |
| Rate limits, queue | see 5 | |
| `PW_BIND_ADDR`, `PW_WEB_ADDR` | `127.0.0.1` | Compose publishes postgres, redis and the api on every interface by default (`docker-compose.yml:63`, `:77`, `:118`). `run_onVM.py` set 127.0.0.1 only in its own process (`run_onVM.py:411`), so a later plain `docker compose up` would have opened them. In `.env` it always applies. |
| `COMPOSE_PROJECT_NAME` | `polar-window` | The name `run_onVM.py` uses (`run_onVM.py:64`): both find the same containers and volume |

### 5. Abuse and cost

- The api limits requests that are not reads, per visitor address per minute
  (`backend/app/api/limits.py:135-152`, wired at `main.py:192-205`). Reads are never limited there
  (`limits.py:11-15`), yet some reads start jobs: the Trip, Contact and Launch sections queue one
  when no answer is stored, and Contact and Launch take any dates. What bounds them: one job per key
  (a unique index on queued and running jobs), and `PW_MAX_QUEUED_JOBS`, past which a new job
  answers 503 with `Retry-After: 60` (`job_service.py:176`, `main.py:307-328`). nginx adds 20
  requests a second per address, burst 200, on `/api/`.
- What a visitor can queue: a section for new dates (contact, launch), a scenario (POST, a write),
  a project's site build (a write). Measured job times on the PC, one worker: contact median 0.6 s
  (max 143 s), launch median 24.1 s (max 131.7 s), scenario median 4.4 s (max 365 s), trip median
  190 s (max 211.8 s).
- Recommended in `deploy/env.production.example` (defaults in brackets): sign-in 10 a minute (60;
  each named sign-in makes a user row, `backend/app/services/auth_service.py:140`); Ask 10 (20; each
  question spends the owner's Gemini quota, up to 4 model rounds, `config.py:297`); writes 30 (120;
  this allowance also covers reading a project file and reading a scenario prompt, which both call
  the model); compare and power runs left at 60 (they move with sliders); queue 60 (200).
- Not settable from `.env`: a daily cap on Gemini use. Watch it in Google AI Studio and turn the AI
  off in Settings if needed. Any signed-in visitor is a project manager and can change Settings,
  including turning the AI off for everyone (`backend/app/api/v1/routes/settings.py:59`).

### 6. The data to copy

- The running app reads under `data/` (`backend/app/config.py:125-161` and the data modules):
  `kernels/` (159 MB), `dem/` without `regional_80m.img` (290 MB), `tiles/` (139 MB), `gravity/`
  (94 MB), `dsn/` (3.4 MB), `spaceweather/` (189 MB), `clps/` (48 MB: flown trips read NASA's
  reconstructed trajectories, `trip_service.py:106-113`), the git-ignored caches in `hindcast/` and
  `climatology/` (13 MB), `sites.json`, and from `external/` only `diviner_prp/index.npz` (32.7 MB,
  `backend/app/data/diviner.py:38`), the PGDA illumination maps `AVGVISIB_*` and `LPSR_*`
  (270.7 MB, `backend/app/data/pgda.py:207-228`) and the 5 m LOLA tiles `*_final_adj_5mpp_{surf,slp,toterr}.tif`
  (1.54 GB, `pgda.py:163-195`, used by `backend/app/services/dispersion_service.py:134-139`).
- Left out (about 1 GB of the 3.7 GB folder): the 605 MB Diviner table (only builds the index), `regional_80m.img` (only
  builds the `.npz`), `SKYV_65S_240M.TIF`, `validation/`, `bulk/`, and `external/` papers, craters,
  images and orbit tables (nothing under `backend/app` or `frontend/src` reads them).
- Why not `run.py --export-data` with `--data-from`: it exports every git-ignored file (3.7 GB
  folder) and imports through `run_onVM.py`, which also prunes and rebuilds. The two tars are
  2.8 GB and go straight into place. The compose `data` step fetches only the core and lifecycle tiers
  (`docker-compose.yml:108`), so the 5 m terrain, the illumination maps, the Diviner index and the
  flown trajectories would not arrive on their own.
- Never shared: `kernels/polar-window.tm` (this PC's Windows paths; the api writes its own at start).
  The orbiter kernels in `kernels/orbiters/` are named by feed snapshot ids, which match because the
  database travels with them.

### 7. First boot and carrying the results

- At every start the api queues the presets of upcoming missions at the lowest priority
  (`backend/app/main.py:124-136`, `:157`; `backend/app/workers/presets.py:80-116`; priorities at
  `backend/app/services/scenario_service.py:46-47`). The PC has 62 preset scenarios and 17 planned
  missions. Without carried results the VM would work them all out again. Measured cost of one full
  re-run on 13 November: 45 scenario jobs, 2,474 s of compute (23 minutes with two workers). With one
  worker that is over 40 minutes in which every visitor's new job waits behind a running preset (up to
  365 s each). It does not exhaust memory, but the first visitors would wait. Hence stage 7 before
  stage 8.
- The keys of stored answers include the catalogue files' bytes (stage 3). Mission records hash
  their parsed content (`backend/app/data/ingest_missions.py:401-404`), so `data/missions.json`'s line
  endings do not matter.
- Recomputed daily by design: a launch search with no chosen dates starts at today's date
  (`backend/app/services/launch_service.py:115-118`), so its key changes each UTC day. At most one
  launch job per planned mission per day, when somebody opens it: 17 jobs, 24.1 s median each.
  Contact answers key on the newest recorded orbiter trajectory (`contact_service.py:142-150`), so
  they are recomputed after the feeds worker records a new one (0.6 s median). Three `im-3` presets
  re-run at every api start (stage 8).

### 8. Staying up

- Reboot: Docker starts at boot (`vm-setup.sh` enables it) and restarts every long-running service.
  postgres and redis had no restart policy, so after a reboot the api would have come back without
  its database; both now have `restart: unless-stopped` (`docker-compose.yml:66`, `:78`).
- Logs: each container's log is capped at 5 x 10 MB (`/etc/docker/daemon.json`); Ubuntu rotates
  nginx's logs.
- Disk growth: `feed_snapshots` grew 22 MB on 12 November (20 MB of raw bodies, 1.6 MB parsed) and
  15 MB on 11 November (9.3 MB raw, 5.4 MB parsed), counted by fetch day on the PC. Raw bodies older
  than 30 days are dropped (`backend/app/workers/feeds.py:30`, `:100-104`), so the database levels
  off near 30 days of raw bodies (about 0.6 GB at 20 MB a day) plus the parsed rows (under 0.4 GB in
  ten weeks at the rates above). The raw bodies do not compress, so a dump is close to the
  database's size (60 MB for 73 MB on 13 November). Backups keep 7 days: up to about 7 GB near the
  end of ten weeks at those rates. The health check writes a warning past 85 % disk use.
- Health: the route is `/healthz` (also `/api/v1/healthz`; `/api/v1/health` is a 404). It answers
  200 for `ok` and `degraded`, 503 for `down` (`backend/app/services/health_service.py:53-58`). The
  timer restarts the api only when it does not answer at all three times in a row. For alerts by
  email, the owner can add a Cloud Monitoring uptime check on `https://polarwindow.ahbab.tech/healthz`.
- Certificate: the certbot package's `certbot.timer` renews; the webroot location stays in the site
  file, and the deploy hook reloads nginx.

### 9. Machine size

- e2-standard-2 (2 vCPU, 8 GB). The api, the compute worker and the feeds worker are each mostly
  one thread (one SPICE thread per process, `docs/runbook.md` section 5; one job at a time per
  worker, `backend/app/workers/compute.py:3-4`). Memory measured on the PC after start: api 268 MB
  (peak 330 MB), compute 182 MB, feeds 114 MB; the peak during a trip job was not measured. The
  dashboard build wants about 4 GB (`run_onVM.py:72`, `:166-169`). 8 GB covers both with room.
- e2-standard-4 (4 vCPU, 16 GB) only if many new answers are asked for at once on judging days, with
  `--scale compute=2`; workers share the queue safely (`compute.py:4-8`).
- Disk 40 GB balanced: data 2.7 GB, the bundle 2.8 GB until stage 10 deletes the tars, the
  database up to about 1 GB, backups up to about 7 GB (see 8), container logs at most 0.3 GB, swap
  2 GB, plus Ubuntu, the images and the build cache (not measured; the backend's Python environment
  is 706 MB on the PC). If `df -h /` passes 85 %, lower `PW_BACKUP_KEEP_DAYS` in the backup unit or
  prune the build cache (Updating later).

## Not checked from the PC

- No Docker on the PC: the images were not built, and build time and image sizes are unknown.
- nginx was not run: the site file follows nginx 1.24 syntax but `nginx -t` runs first on the VM.
- The restore was tested on PostgreSQL 16.11 for Windows, not on `postgres:16-alpine`.
- How fast a VM core is against the PC's i5-10400, so every job time above may be longer on the VM.
- Whether the GitHub repository is public.
