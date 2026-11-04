# MAKTECH SiteScore

A free, public website check by MAKTECH: **is your website AI agent ready?** A visitor enters their email address (checked for a valid format, a domain that accepts mail and no throwaway inboxes), scans a website, and gets two scores out of 100 with every finding explained in plain language:

- **AI agent readiness** (6 checks, shown first): robots.txt, sitemap, Link headers, Markdown for agents, AI crawler rules and Content Signals, the open standards AI assistants use to find and read sites. llms.txt is shown too, but not scored. The checks follow Cloudflare's agent readiness scanner (isitagentready.com, content-site profile) and were compared with it on real sites.
- **Website health** (23 checks): security, reliability, email, performance and search basics. The speed test runs on our own worker in a real browser (Lighthouse). If a site turns that browser away (bot protection, a firewall), Google PageSpeed Insights is asked instead, when a key is set.

Anyone can check any website; the only requirement is a valid email address, where the PDF report goes.

A branded PDF report follows by email, and every lead appears in a sales dashboard.

| | Address |
| --- | --- |
| Web app | https://sitescore.maktechgroup.com |
| Sales dashboard | https://sitescore.maktechgroup.com/admin |
| API | https://api-sitescore.maktechgroup.com |

## Contents

1. [How it fits together](#1-how-it-fits-together)
2. [Repository layout](#2-repository-layout)
3. [Environment variables](#3-environment-variables)
4. [Deploying on Coolify, step by step](#4-deploying-on-coolify-step-by-step)
5. [After the first deploy](#5-after-the-first-deploy)
6. [Running it day to day](#6-running-it-day-to-day)
7. [Troubleshooting](#7-troubleshooting)
8. [Local development and tests](#8-local-development-and-tests)
9. [Where to change things](#9-where-to-change-things)

## 1. How it fits together

```
 Visitor's browser ──► sitescore-web (nginx, static React app)       sitescore.maktechgroup.com
        │
        └──────────► sitescore-api (FastAPI)                          api-sitescore.maktechgroup.com
                         │  saves leads and scans        ┌──────────────┐
                         ├──────────────────────────────►│ PostgreSQL 16│
                         │  queues scan jobs             └──────────────┘
                         ▼                                      ▲
                     Redis 7 ◄──── sitescore-worker ────────────┘
                                   runs the 29 checks and the speed test (Chromium + Lighthouse),
                                   builds the PDF, sends the emails
```

- **sitescore-web** serves the website and the sales dashboard. It holds no secrets.
- **sitescore-api** handles sign-in, starts scans, serves results and PDFs, and runs the database migrations when it starts.
- **sitescore-worker** is the same image as the API with `SITESCORE_ROLE=worker`. It runs several scan workers and sends the report emails. The speed test runs here too: Lighthouse loads the homepage in headless Chromium as a mid-range phone on 4G. Every connection that browser makes goes through a small built-in filter that allows public web servers only, so a scanned page can never make it reach internal addresses.
- **PostgreSQL** stores leads, scans and staff accounts. **Redis** holds the job queue and the rate limits.

Both domains sit under `maktechgroup.com`, so browsers treat them as one site: the visitor's sign-in cookie lives on the API domain and is sent with every call from the web app. The API accepts calls only from the origins in `SITESCORE_CORS_ORIGINS`.

## 2. Repository layout

```
backend/                  Python 3.12
  Dockerfile              one image for the API and the worker
  docker/                 entrypoint (picks api or worker) and health check
  migrations/             Alembic database migrations
  sitescore/
    engine/               the scanner: 6 AI agent checks and 23 health checks, two scores,
                          plain-language findings, the speed test (speedtest.py, egress.py)
    api.py                public API
    admin.py              sales dashboard API
    scans.py              scan jobs and report delivery
    report.py             PDF report and report email
    templates/            PDF and email templates
    assets/               logo and the bundled Inter font
  tests/                  181 tests, run offline (one runs a real browser when Lighthouse is installed)
  requirements.txt        exact versions installed in the image
  .env.example            every setting, with comments
frontend/                 React + Vite + Tailwind
  Dockerfile              builds the app and serves it with nginx
  nginx/                  nginx config template (security headers, page routing)
  src/pages/              Home, ScanPage, About/Privacy/Terms, admin/
.github/workflows/ci.yml  tests, web build and both Docker builds on every push
```

## 3. Environment variables

The **When** column says when a variable is read:

- **Build**: baked into the image while it is built. Changing it needs a rebuild.
- **Runtime**: read when the container starts. Changing it needs a restart (in Coolify: redeploy).
- **Both**: needed while building and read again when the container starts.

The backend image needs **no build variables**. The web app needs exactly **one**, used at **both** stages.

### 3.1 Web app (`sitescore-web`)

| Variable | When | Required | Value | What it does |
| --- | --- | --- | --- | --- |
| `VITE_API_BASE` | **Both** | Yes | `https://api-sitescore.maktechgroup.com` | Build: baked into the JavaScript as the address for API calls. Runtime: written into the page's Content-Security-Policy header, so browsers allow those calls. No trailing slash. |

In Coolify, add it once and make sure it is available at **build time** (tick *Build Variable*, called *Available at Buildtime* in newer Coolify versions) as well as at runtime, which is the default.

### 3.2 API and worker: required

All **Runtime**. Give `sitescore-api` and `sitescore-worker` the same values (step 4.4 shows how to share them).

| Variable | Example or where to get it | What it does |
| --- | --- | --- |
| `SITESCORE_ROLE` | `api` on sitescore-api, `worker` on sitescore-worker | What the container runs. The only value that differs between the two apps. |
| `SITESCORE_SECRET_KEY` | run `python3 -c "import secrets;print(secrets.token_urlsafe(48))"` | Signs the visitor and staff session cookies. 40+ characters. Changing it signs everyone out. |
| `SITESCORE_DATABASE_URL` | `postgres://USER:PASS@HOST:5432/DB` | Coolify's internal Postgres URL, pasted as it is (step 4.2). `postgres://`, `postgresql://` and `postgresql+asyncpg://` all work. |
| `SITESCORE_REDIS_URL` | `redis://default:PASS@HOST:6379/0` | Coolify's internal Redis URL. |
| `SITESCORE_SMTP_HOST` | `mail.maktechgroup.com` | Mail server for sitescore@maktechgroup.com. |
| `SITESCORE_SMTP_PORT` | `587` (STARTTLS) or `465` (SSL) | Port 465 switches to SSL automatically. Default `587`. |
| `SITESCORE_SMTP_USER` | `sitescore@maktechgroup.com` | SMTP login. |
| `SITESCORE_SMTP_PASSWORD` | from your mail provider | SMTP password. |

If a required value is missing or unsafe, the container **refuses to start** and its log lists exactly what to fix, for example `SITESCORE_SMTP_HOST, SITESCORE_SMTP_USER and SITESCORE_SMTP_PASSWORD must be set.`

### 3.3 API and worker: optional

All **Runtime**. The defaults are already set for MAKTECH; set a variable only to change it.

| Variable | Default | What it does |
| --- | --- | --- |
| `SITESCORE_ENV` | `production` (set by the image) | `development` relaxes the start-up checks. Never on the live server. |
| `SITESCORE_PUBLIC_BASE_URL` | `https://sitescore.maktechgroup.com` | Web app address used in links inside emails and PDFs. |
| `SITESCORE_CORS_ORIGINS` | `https://sitescore.maktechgroup.com` | Web app origins allowed to call the API. Comma separated, https only. |
| `SITESCORE_MAIL_FROM` | `MAKTECH SiteScore <sitescore@maktechgroup.com>` | Sender. Replies to report emails arrive in this same inbox. |
| `SITESCORE_SMTP_STARTTLS` | `true` | Use STARTTLS on port 587. Ignored on 465. |
| `SITESCORE_WHATSAPP_NUMBER` | `8801897669234` | "Chat on WhatsApp" button and the QR code in the PDF. Country code first, digits only. |
| `SITESCORE_CONTACT_PHONE` | `8801897669234` | "Call us" button on the results page, and the phone number in the PDF. Country code first, digits only. |
| `SITESCORE_OFFER_PRICE_USD`, `SITESCORE_OFFER_PRICE_BDT` | `40`, `5000` | One-time price of the Fix-It Starter Pack, shown on the results page (visitors switch between USD and BDT) and in the PDF. Whole numbers only. |
| `SITESCORE_COMPANY_ADDRESS` | `8th Floor, A, Majid Tower, Ka-24 Progati Sarani Rd, Dhaka 1229, Bangladesh` | Printed in emails and the PDF. |
| `SITESCORE_BLOCKED_NETWORKS` | empty | Extra address ranges the scanner must never touch, such as MAKTECH's internal networks: `10.0.0.0/8,172.16.0.0/12`. Private and reserved ranges are always blocked. |
| `SITESCORE_OPT_OUT_DOMAINS` | empty | Domains whose owners asked not to be scanned, comma separated. |
| `SITESCORE_TURNSTILE_SITE_KEY`, `SITESCORE_TURNSTILE_SECRET` | empty (off) | Cloudflare bot check on the sign-up form. See 6.6. |
| `SITESCORE_CLIENT_IP_HEADER` | empty | Set to `CF-Connecting-IP` only if Cloudflare proxies the API (orange cloud). |
| `SITESCORE_TRUSTED_PROXY_HOPS` | `1` | Proxies in front of the API that append to `X-Forwarded-For`. Coolify's proxy counts as 1. |
| `SITESCORE_DNSBL_ZONES` | `bl.spamcop.net,psbl.surriel.com,b.barracudacentral.org` | Spam blocklists checked for the scanned site's mail server. Empty turns the check off. |
| `SITESCORE_LEAD_RETENTION_DAYS` | `365` | Leads not marked Won are deleted after this many days (6.3). |
| `SITESCORE_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |
| `WEB_CONCURRENCY` | `2` | API only: number of API processes. |
| `WORKER_COUNT` | `4` | Worker only: how many scans can run at the same time. |
| `SITESCORE_SPEED_TEST_SLOTS` | `2` | Worker only: how many speed tests may run at once. Each needs about one CPU core and 500 MB of memory; more at once slows them all and makes scores worse. Rule of thumb: one per two CPU cores. Other scans wait for a free slot. |
| `SITESCORE_SPEED_TEST_TIMEOUT` | `240` | Worker only: seconds a speed test may take, including waiting for a free slot and one retry. |
| `SITESCORE_SPEED_TEST_MIN_FREE_MB` | `600` | Worker only: a speed test starts only when this much memory is free, so a busy server never runs out of memory. |
| `SITESCORE_PSI_API_KEY` | empty | Worker only, optional but recommended: a Google PageSpeed Insights API key (Google Cloud Console > APIs & Services > PageSpeed Insights API > Credentials). Used only as a backup, when our own test browser cannot load a site (bot protection, firewalls). Without it those sites show the speed checks as *not checked*. |

The image sets `SITESCORE_CHROME_PATH` and `SITESCORE_LIGHTHOUSE_CMD` itself. `SITESCORE_REPORT_DELAY_SECONDS` no longer exists (the backup question is gone): delete it from Coolify if it is set.

Abuse limits, also **Runtime**, with sensible defaults:

| Variable | Default |
| --- | --- |
| `SITESCORE_SIGNUPS_PER_IP_PER_HOUR` | `20` |
| `SITESCORE_SCANS_PER_LEAD_PER_DAY`, `SITESCORE_SCANS_PER_IP_PER_DAY` | `5`, `10` (raise both for an exhibition, see 6.9) |
| `SITESCORE_PDF_DOWNLOADS_PER_IP_PER_HOUR` | `30` |
| `SITESCORE_STAFF_LOGINS_PER_IP_PER_HOUR` | `20` |
| `SITESCORE_RESULTS_LINK_DAYS`, `SITESCORE_SESSION_DAYS`, `SITESCORE_STAFF_SESSION_HOURS` | `30`, `30`, `12` |

Development only, never in production: `SITESCORE_QUEUE_MODE=inline`, `SITESCORE_COOKIE_SECURE=false`, `SITESCORE_AUTO_CREATE_TABLES=true`, `SITESCORE_EMAIL_CHECK_DELIVERABILITY=false`.

## 4. Deploying on Coolify, step by step

You will create five resources in one Coolify project, all on the same server:

| Resource | Type | Base directory | Domain | Port |
| --- | --- | --- | --- | --- |
| `sitescore-db` | PostgreSQL 16 | | none | |
| `sitescore-redis` | Redis 7 | | none | |
| `sitescore-api` | Application, Dockerfile | `/backend` | `https://api-sitescore.maktechgroup.com` | `8000` |
| `sitescore-worker` | Application, Dockerfile | `/backend` | none | none |
| `sitescore-web` | Application, Dockerfile | `/frontend` | `https://sitescore.maktechgroup.com` | `80` |

Create and deploy them in that order: databases, API, worker, web app.

### 4.1 Before you start

1. **Push the code** to your GitHub repository and wait for the **CI** run in the Actions tab to go green. It runs the tests and builds both Docker images, so a green run means Coolify can build them too.
2. **DNS**: add two A records pointing at the Coolify server's public IP address:
   ```
   sitescore.maktechgroup.com       A   <server IP>
   api-sitescore.maktechgroup.com   A   <server IP>
   ```
   If the domain is on Cloudflare, start with *DNS only* (grey cloud) so Coolify can get its certificates. If you turn the proxy on later, use SSL mode *Full (strict)* and set `SITESCORE_CLIENT_IP_HEADER=CF-Connecting-IP` on the API and worker.
3. **Outbound network**: the worker must reach the internet on TCP 80 and 443 (websites, including everything the speed-test browser loads, and domain registries), on UDP and TCP 53 (DNS, including direct queries to nameservers), and on your SMTP port. The API needs your SMTP port too.
4. **Email authentication for maktechgroup.com**: the domain's SPF and DKIM records must cover the server that sends for sitescore@maktechgroup.com, and the domain should have a DMARC record. Otherwise reports land in spam, and SiteScore would flag our own domain.
5. **Have ready**: the SMTP host, port and password, and a new secret key from `python3 -c "import secrets;print(secrets.token_urlsafe(48))"`.

### 4.2 Create the databases

1. In Coolify: **Projects > + Add**, name it `SiteScore`, and open its `production` environment.
2. **+ New > Database > PostgreSQL**, choose version 16, name it `sitescore-db`, then **Start**.
3. Copy its **Postgres URL (internal)**, which looks like this:
   ```
   postgres://postgres:PASSWORD@abc123xyz:5432/postgres
   ```
   That is your `SITESCORE_DATABASE_URL`. Paste it unchanged: the app switches it to its own Postgres driver.
   Use the *internal* URL, not the public one, so database traffic never leaves the server.
4. In the database's **Backups** tab, schedule a daily backup (to S3-compatible storage if you have it).
5. **+ New > Database > Redis**, version 7, name it `sitescore-redis`, **Start**, and copy its **Redis URL (internal)**. That is your `SITESCORE_REDIS_URL`.

### 4.3 Create the API (`sitescore-api`)

1. **+ New > Application**, pick your GitHub repository (through the GitHub App, or *Private Repository* with a deploy key) and the branch.
2. **Build Pack**: `Dockerfile`. **Base Directory**: `/backend`. **Dockerfile Location**: `/Dockerfile`.
3. **Name**: `sitescore-api`. **Domains**: `https://api-sitescore.maktechgroup.com`. **Ports Exposes**: `8000`.
4. **Environment Variables**: every variable in 3.2 with `SITESCORE_ROLE=api`, plus any optional ones from 3.3 you want. At least set `SITESCORE_BLOCKED_NETWORKS` to MAKTECH's internal ranges. None of these is a build variable: untick *Build Variable* (*Available at Buildtime*) on every one, so secrets are never passed into the image build. If you leave it ticked the build still works, but Docker prints `SecretsUsedInArgOrEnv` warnings.
5. **Health check**: on, path `/api/health`, port `8000`.
6. Optional: **Watch Paths** `backend/**`, so changes to the web app alone do not redeploy the API.
7. **Deploy**. The log should show `Settings look good.`, then `Running upgrade` lines up to `0003` (the database tables being created or updated), then Uvicorn starting.
8. Open https://api-sitescore.maktechgroup.com/api/health. It must show `{"status":"ok"}`.

### 4.4 Create the worker (`sitescore-worker`)

1. **+ New > Application**, same repository and branch.
2. **Build Pack**: `Dockerfile`. **Base Directory**: `/backend`. **Dockerfile Location**: `/Dockerfile`.
3. **Name**: `sitescore-worker`. Leave **Domains** empty: it serves no web traffic. If Coolify asks for a port, leave `8000`; nothing is exposed without a domain.
4. **Environment Variables**: the same as the API, except `SITESCORE_ROLE=worker`, plus `WORKER_COUNT=4` (or `10` for ten scans at once, see 6.8).

   To avoid entering secrets twice, put the shared values in **Project > Environment > Shared Variables** and reference them in both apps as `{{environment.SITESCORE_DATABASE_URL}}` and so on.
5. **Health check**: leave Coolify's HTTP health check off for this app. The image has its own check that pings Redis.
6. Optional: **Watch Paths** `backend/**`.
7. **Deploy**. The log should show `Settings look good.` followed by four workers starting.

### 4.5 Create the web app (`sitescore-web`)

1. **+ New > Application**, same repository and branch.
2. **Build Pack**: `Dockerfile`. **Base Directory**: `/frontend`. **Dockerfile Location**: `/Dockerfile`.
3. **Name**: `sitescore-web`. **Domains**: `https://sitescore.maktechgroup.com`. **Ports Exposes**: `80`.
4. **Environment Variables**: `VITE_API_BASE=https://api-sitescore.maktechgroup.com`, available at build time and at runtime (3.1).
5. **Health check**: on, path `/healthz`, port `80`.
6. Optional: **Watch Paths** `frontend/**`.
7. **Deploy**, then open https://sitescore.maktechgroup.com.

### 4.6 Daily clean-up task

On **sitescore-api > Scheduled Tasks > + Add**:

| Field | Value |
| --- | --- |
| Name | `cleanup` |
| Command | `python -m sitescore cleanup` |
| Frequency | `0 3 * * *` (every day at 03:00) |

It deletes leads (and their scans) older than 12 months unless they are marked Won, exactly as the Privacy page promises.

### 4.7 Create the first staff account

Open **sitescore-api > Terminal** and run:

```bash
python -m sitescore create-staff you@maktechgroup.com --name "Your name" --role admin
```

Enter a password of 12 or more characters. Then sign in at https://sitescore.maktechgroup.com/admin. The first sign-in shows a QR code: scan it with Google Authenticator or Microsoft Authenticator and enter the 6-digit code. Every later sign-in asks for the password and a code from the app.

## 5. After the first deploy

Work through this list before telling anyone about SiteScore:

- [ ] https://api-sitescore.maktechgroup.com/api/health shows `{"status":"ok"}`.
- [ ] On your phone, open https://sitescore.maktechgroup.com, enter your email, scan one of our own sites, and receive the PDF report by email (check spam the first time).
- [ ] The scan finishes in a minute or two and the results page shows the AI agent readiness score first, then the health score with a mobile speed result (not "not checked").
- [ ] In the worker terminal, `python -m sitescore test-speed maktechgroup.com` prints a mobile speed score.
- [ ] The PDF report arrives by email within a minute of the scan finishing, and *Download PDF* works.
- [ ] Tap *Request a call*; the lead appears at the top of https://sitescore.maktechgroup.com/admin marked *Wants a call*.
- [ ] Share a results link on WhatsApp; the SiteScore preview image appears.
- [ ] **Scan about 20 MAKTECH-built sites** and check every finding by hand. The DNS, email and DNSSEC checks have only been tested against simulated data so far; the AI agent checks and the speed test were tried on real sites.

## 6. Running it day to day

### 6.1 Staff accounts

Run these in **sitescore-api > Terminal**:

```bash
python -m sitescore create-staff sales1@maktechgroup.com --name "Rahim"     # new account, or reset a password
python -m sitescore reset-staff-2fa sales1@maktechgroup.com                # lost phone: set up the app again
python -m sitescore disable-staff sales1@maktechgroup.com                  # someone left
python -m sitescore set-staff-role you@maktechgroup.com admin              # admin: can clear all leads
```

Deleting leads: open a lead and use *Delete this lead* at the bottom (any staff account). *Clear all* on the leads list deletes every lead and scan; it is shown only to admin accounts and asks you to type `DELETE ALL`. Both cannot be undone, so export the CSV first if you need a copy.

### 6.2 Report emails

The PDF report is emailed the moment a scan finishes. Each scan on a lead's page in the dashboard shows *Report emailed*, *Report being sent* or *Report not delivered yet* with the mail server's reason, and a button to send it again. Failed sends are also retried automatically after 1, 5 and 15 minutes.

To check email from the server, run these in **sitescore-worker > Terminal** (the worker is what sends reports):

```bash
python -m sitescore send-test-email you@maktechgroup.com                   # proves SMTP works, or prints why not
python -m sitescore send-report https://sitescore.maktechgroup.com/scan/TOKEN   # email one report again now
```

### 6.3 Data retention

The daily `cleanup` task (4.6) keeps the promises made on the Privacy page. To run it by hand, run `python -m sitescore cleanup` in the API terminal.

### 6.4 Updating

Push to GitHub, wait for CI to pass, then redeploy in Coolify (or turn on automatic deploys). Database changes ship as Alembic migrations and run automatically when the API starts. When a release changes the database, deploy **the API first**, then the worker. To roll back, redeploy an earlier deployment from the app's **Deployments** tab.

### 6.5 Owners who ask not to be scanned

Add their domain to `SITESCORE_OPT_OUT_DOMAINS` on the API (comma separated) and redeploy it.

### 6.6 Turning on the bot check later (Cloudflare Turnstile)

SiteScore runs without it, using per-IP limits on sign-ups and scans, a check that the email domain accepts mail, and a block on throwaway email domains. There is no code by email, so anyone can type any address, and the report for a scan goes to the address typed. If the dashboard shows sign-ups with addresses that look made up, or people tell us they received reports they never asked for, turn Turnstile on.

1. Cloudflare dashboard > **Turnstile > Add site**, domain `sitescore.maktechgroup.com`, widget mode *Managed*.
2. Add `SITESCORE_TURNSTILE_SITE_KEY` and `SITESCORE_TURNSTILE_SECRET` to the API and redeploy it. The form shows the check automatically; the web app needs no change.
3. Add a line about Cloudflare to the Privacy page under *Who else sees it* (`frontend/src/pages/InfoPages.tsx`).

### 6.7 Monthly upkeep

- Update `backend/sitescore/engine/data/software_versions.json` with the oldest supported PHP, WordPress, Drupal and Joomla versions. PHP 8.2 loses security support on 31 December 2026: change `"php": "8.2"` to `"8.3"` in January 2027.
- Glance at the API and worker logs for warnings.

### 6.8 Scaling and ten scans at once

Each scan is a worker. Most of a scan is waiting on the network and costs little; the speed test is the heavy part: a real browser that needs about one CPU core and 500 MB of memory for 15 to 45 seconds. `WORKER_COUNT` sets how many scans run at once, `SITESCORE_SPEED_TEST_SLOTS` how many speed tests run at once (the rest queue for a few seconds).

Measured with 10 real websites scanned at the same moment through the worker image:

| Server (whole machine) | Worker settings | 10 scans finish in | Peak worker memory |
| --- | --- | --- | --- |
| 2 vCPU, 8 GB | `WORKER_COUNT=10`, `SITESCORE_SPEED_TEST_SLOTS=1` | about 3.5 minutes | 1.9 GB |
| 2 vCPU, 8 GB | `WORKER_COUNT=10`, `SITESCORE_SPEED_TEST_SLOTS=2` | about 2.5 minutes (CPU overloaded, one speed test ran out of time) | 3.1 GB |

So, for ten scans at once:

- **Minimum:** 4 vCPU and 8 GB RAM, with `WORKER_COUNT=10` and `SITESCORE_SPEED_TEST_SLOTS=2`. All ten finish within about 3 minutes.
- **Recommended (exhibitions, busy days):** 8 vCPU and 16 GB RAM, with `WORKER_COUNT=10` and `SITESCORE_SPEED_TEST_SLOTS=4`. All ten finish within about 2 minutes, with headroom for the API, PostgreSQL, Redis and Coolify on the same server.

If Coolify has a memory limit on the worker, give it at least 4 GB (or 6 GB with 4 slots). Keep a single API container, because it runs the migrations when it starts.

### 6.9 Exhibition day

Everyone at a stall shares one Wi-Fi address, so the per-address limits must be raised for the day (on the API and the worker), then put back afterwards:

```
SITESCORE_SCANS_PER_IP_PER_DAY=1000
SITESCORE_SCANS_PER_LEAD_PER_DAY=100
SITESCORE_SIGNUPS_PER_IP_PER_HOUR=500
```

Also: run `python -m sitescore set-staff-role you@maktechgroup.com admin` and *Clear all* on the leads list to start the day with an empty dashboard (export the CSV first), scan `sitescore.maktechgroup.com` once to warm everything up, and keep `python -m sitescore test-speed example.com` handy in the worker terminal.

### 6.10 SiteScore scoring 100 on itself

The web app serves everything its own AI agent checks look for: `robots.txt` with AI crawler rules and Content Signals, `sitemap.xml`, `llms.txt`, Markdown for agents (`Accept: text/markdown` returns `index.md`), Link headers on the home page, and `/.well-known/security.txt` (the sitemap and security.txt are written fresh on every build). Its speed test scores about 97 (largest content under 2.5 s, almost no blocking time).

Two things live outside the code, in DNS for maktechgroup.com, and both affect the health score:

- **DNSSEC** is off. In Cloudflare: DNS > Settings > *Enable DNSSEC*, then add the DS record it shows at your domain registrar. This is the last point between SiteScore and 100.
- SPF, DKIM (selector `dkim`) and DMARC (`p=quarantine`) are already in place, and the mail server is on no blocklist.

## 7. Troubleshooting

| Symptom | Likely cause and fix |
| --- | --- |
| Container stops right after starting with `SiteScore cannot start in production` | The log lists each missing or unsafe setting. Fix them and redeploy. |
| Deploy log says *The healthcheck needs a curl or wget command* | Coolify prints this for every Dockerfile app. Both images include the tool, so ignore it; the real reason for a failed deploy is in the *Container logs* section just above it. |
| `relation "leads" does not exist` | The API has not run its migrations yet. Deploy the API before the worker. |
| Web app shows *Could not reach SiteScore* | `VITE_API_BASE` is wrong or was not available at build time. Fix it and redeploy the web app so it rebuilds. |
| Browser console shows a CORS error | `SITESCORE_CORS_ORIGINS` on the API must be exactly `https://sitescore.maktechgroup.com`. |
| After entering an email, the form keeps asking for it again | The session cookie was not stored. Both sites must be on https, and `SITESCORE_COOKIE_SECURE` must not be false. |
| A real email address is refused as not valid | The API checks that the address's domain accepts mail with a DNS lookup. If the API cannot reach DNS, every address fails: check the API container's network. |
| Reports never arrive | Run `python -m sitescore send-test-email you@maktechgroup.com` in the worker terminal: it prints the exact SMTP problem. The lead's page in the dashboard shows why a report failed. If the test email arrives in spam, fix SPF and DKIM for maktechgroup.com. |
| The worker container keeps restarting | Fixed in this version: the workers now run as a pool, so one worker stopping (a lost Redis connection, or the kernel ending it when memory ran out) no longer restarts the whole container; the health check allows a busy CPU 15 seconds; speed tests wait for free memory. If it still happens, check the worker's memory limit in Coolify (6.8) and the log lines just before the restart. |
| Scans stay on *Starting your scan* and fail after 8 minutes | The worker is not running or cannot reach Redis. Check the `sitescore-worker` logs and `SITESCORE_REDIS_URL`. |
| Many checks show *not checked* | The worker cannot reach DNS or the internet (4.1, step 3). |
| The two speed checks show *not checked* | Run `python -m sitescore test-speed the-site.com` in the worker terminal: it prints the exact error. The lead's page in the dashboard shows it too, under the scan. `busy` means every speed-test slot stayed taken: raise `SITESCORE_SPEED_TEST_SLOTS` if the server has spare CPU. `NO_FCP` or `ERRORED_DOCUMENT_REQUEST` mean the site itself did not load in the browser; *bot protection or firewall* means the site turned the test browser away. With `SITESCORE_PSI_API_KEY` set, both fall back to Google PageSpeed Insights. |
| Speed scores differ from Google PageSpeed Insights | Both run Lighthouse on a simulated mid-range phone, but on different hardware, and either moves a few points between runs. Pages built on WebGL (3D animations) can differ more: a server has no graphics chip, so the test browser switches 3D graphics off rather than drawing them slowly in software. |
| Everyone gets *Too many tries from your network* or *today's free scan limit* | The API is not seeing real visitor addresses. If Cloudflare proxies the API, set `SITESCORE_CLIENT_IP_HEADER=CF-Connecting-IP`. |
| A staff member lost their phone | Run `python -m sitescore reset-staff-2fa their@email` in the API terminal. |

## 8. Local development and tests

Needs Python 3.12, Node 22, PostgreSQL and Redis.

```bash
# API on http://localhost:8077 (interactive docs at /api/docs)
cd backend
pip install -e ".[dev]"
cp .env.example .env      # then set SITESCORE_ENV=development and SITESCORE_COOKIE_SECURE=false,
                          # and point the database and Redis URLs at your local services
alembic upgrade head
python -m sitescore create-staff you@maktechgroup.com --name "You"
uvicorn sitescore.api:app --port 8077

# Worker, in a second terminal
rq worker sitescore --with-scheduler --url redis://localhost:6379/0

# Web app on http://localhost:5173, in a third terminal (calls /api through Vite's proxy)
cd frontend
npm install
npm run dev
```

In development without SMTP settings, reports are printed in the API log instead of being emailed.

Try the scanner on its own: `python -m sitescore scan example.com` (add `--json` or `--no-speed`). Run just the speed test with `python -m sitescore test-speed example.com`. On your own machine the speed test needs Lighthouse (`npm install -g lighthouse@13.5.0`) and Chrome or Chromium; set `SITESCORE_CHROME_PATH` if Chromium is not found.

Tests:

```bash
cd backend && python -m pytest -q     # 133 tests, offline: DNS and HTTP are faked
cd frontend && npm run build          # type check and production build
```

The same checks, plus both Docker builds, run in GitHub Actions on every push (`.github/workflows/ci.yml`).

## 9. Where to change things

| What | Where |
| --- | --- |
| Wording of every finding | `backend/sitescore/engine/findings.py` |
| Points per check | the `@check(...)` lines in `backend/sitescore/engine/checks/*.py` |
| Oldest supported software versions | `backend/sitescore/engine/data/software_versions.json` |
| Throwaway email domains | `backend/sitescore/data/disposable_domains.txt` |
| PDF report layout | `backend/sitescore/templates/report.html` |
| Report emails | `backend/sitescore/templates/report_email.html`, `backend/sitescore/mailer.py` |
| About, Privacy and Terms pages | `frontend/src/pages/InfoPages.tsx` |
| Footer (links, credit line) | `frontend/src/components/Footer.tsx` |
| Colours, light and dark themes, glass style | the tokens at the top of `frontend/src/index.css` (one block per theme) |
| Animations (page entrances, sheet, scroll reveals) | `frontend/src/motion.tsx` and the components that use it; built with Motion. Visitors who turn on Reduce Motion get no movement |
| Theme switching (Automatic, Light, Dark) | `frontend/src/theme.ts`, `frontend/src/components/ThemeToggle.tsx`, and `frontend/theme-boot.js`, which sets the theme before the page paints (inlined into the page at build time; if you change it, the build prints the new hash to put in `nginx/default.conf.template`) |
| Sharing preview image | `frontend/public/og-image.png` (1200 x 630; give a new image a new file name so WhatsApp and Facebook fetch it fresh) |
| Web app security headers | `frontend/nginx/default.conf.template` |
| Database tables | edit `backend/sitescore/db.py`, then run `alembic revision --autogenerate -m "what changed"` |

The report font, Inter, is bundled under the SIL Open Font License (`backend/sitescore/assets/fonts/OFL.txt`).
