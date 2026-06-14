# Deploying ml-theses.org

The site is a **static** MkDocs Material build. The repo's source-of-truth
files (`README.md`, `Topics.md`, `theses.csv`) are assembled by
[`build_site.sh`](build_site.sh) into `site/`, which is served by nginx on a
Hetzner VPS. Every push to `main` rebuilds and deploys via GitHub Actions.

```
theses.csv ─┐
README.md  ─┼─► build_site.sh ─► site/ ─► (rsync over SSH) ─► Hetzner nginx ─► https://ml-theses.org
Topics.md  ─┘        ▲
                MkDocs Material
```

## 1. Local preview

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-docs.txt
./build_site.sh serve        # live preview at http://127.0.0.1:8000
./build_site.sh              # one-off build into site/
```

You normally only ever hand-edit `theses.csv`, `README.md`, or `Topics.md`.
`docs/`, `site/`, and `theses.md` are regenerated and git-ignored.

## 2. DNS (domain registrar)

Point the domain at the Hetzner server's IP:

| Type | Name | Value            |
|------|------|------------------|
| A    | `@`  | `<server-IPv4>`  |
| AAAA | `@`  | `<server-IPv6>`  (if available) |
| A    | `www`| `<server-IPv4>`  |

## 3. One-time server setup (Hetzner)

SSH in as root and run:

```bash
apt update && apt install -y nginx rsync certbot python3-certbot-nginx

# Dedicated, unprivileged deploy user that owns the web root
adduser --disabled-password --gecos "" deploy
mkdir -p /var/www/ml-theses
chown -R deploy:deploy /var/www/ml-theses

# Let nginx (www-data) read files written by deploy
usermod -aG deploy www-data
chmod 750 /var/www/ml-theses
```

### nginx server block

Create `/etc/nginx/sites-available/ml-theses`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name ml-theses.org www.ml-theses.org;

    root /var/www/ml-theses;
    index index.html;

    # MkDocs is built with use_directory_urls: false, so request paths map
    # directly to .html files.
    location / {
        try_files $uri $uri.html $uri/ =404;
    }

    error_page 404 /404.html;

    # Long cache for fingerprinted assets; HTML stays fresh.
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable it and obtain TLS:

```bash
ln -s /etc/nginx/sites-available/ml-theses /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# Free Let's Encrypt certificate + auto-redirect to HTTPS + auto-renewal
certbot --nginx -d ml-theses.org -d www.ml-theses.org
```

## 4. Deploy key (server ⇄ GitHub Actions)

On your **laptop**, create a dedicated key pair for CI:

```bash
ssh-keygen -t ed25519 -f ml-theses-deploy -N "" -C "github-actions"
```

- Add the **public** key to the server's deploy user:
  ```bash
  ssh-copy-id -i ml-theses-deploy.pub deploy@<server-IP>
  # or append ml-theses-deploy.pub to /home/deploy/.ssh/authorized_keys
  ```
- Add the **private** key (`ml-theses-deploy`) as the `SSH_PRIVATE_KEY` secret below, then delete both local copies.

## 5. GitHub repository secrets

In **Settings → Secrets and variables → Actions**, add:

| Secret            | Value                                   |
|-------------------|-----------------------------------------|
| `SSH_PRIVATE_KEY` | Contents of `ml-theses-deploy` (private)|
| `SSH_HOST`        | Server IP or `ml-theses.org`            |
| `SSH_USER`        | `deploy`                                |
| `DEPLOY_PATH`     | `/var/www/ml-theses/`  (trailing slash) |

## 6. Go live

Push to `main`. The [deploy workflow](.github/workflows/deploy.yml) builds the
site and rsyncs it to the server. Watch progress under the repo's **Actions**
tab. After it succeeds, visit <https://ml-theses.org>.

To update content later: edit `theses.csv` / `README.md` / `Topics.md`, commit,
push. That's the entire workflow.

## Troubleshooting

- **403 from nginx** — `www-data` can't read the files. Re-check the `usermod
  -aG deploy www-data` step and that `/var/www/ml-theses` is group-readable.
- **CI fails at "Build site"** — a broken internal link (`--strict`). The error
  names the offending file and link; fix it in the source markdown.
- **CI fails at rsync** — wrong/expired `SSH_PRIVATE_KEY`, or the public key
  isn't in `deploy`'s `authorized_keys`, or `SSH_HOST` host key changed.
