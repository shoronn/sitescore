# MAKTECH SiteScore backend: one image, two roles.
#   SITESCORE_ROLE=api     FastAPI on port 8000 (runs database migrations first)
#   SITESCORE_ROLE=worker  scan and email workers (no port), including the speed test

# The speed test runs Lighthouse, a Node.js tool. It is installed here and copied below.
FROM node:22-bookworm-slim AS lighthouse
RUN npm install -g --omit=dev --no-audit --no-fund lighthouse@13.5.0 \
 && npm cache clean --force

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SITESCORE_ROLE=api \
    SITESCORE_ENV=production

# WeasyPrint needs Pango and HarfBuzz. The report font (Inter) ships inside the app.
# Chromium runs the speed test; the Noto fonts cover Bengali, Latin and emoji, so pages
# lay out (and score) as they do for real visitors.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 \
      fonts-dejavu-core curl tini \
      chromium fonts-liberation fonts-noto-core fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

COPY --from=lighthouse /usr/local/bin/node /usr/local/bin/node
COPY --from=lighthouse /usr/local/lib/node_modules/lighthouse /opt/lighthouse
RUN ln -s /opt/lighthouse/cli/index.js /usr/local/bin/lighthouse \
 && lighthouse --version && chromium --version
ENV SITESCORE_CHROME_PATH=/usr/bin/chromium \
    SITESCORE_LIGHTHOUSE_CMD=lighthouse

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml alembic.ini ./
COPY migrations ./migrations
COPY sitescore ./sitescore
RUN pip install --no-deps . \
 && useradd --system --uid 10001 --home /app sitescore \
 && chown -R sitescore /app

COPY docker/entrypoint.sh docker/healthcheck.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/healthcheck.sh

USER sitescore
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 CMD ["healthcheck.sh"]
ENTRYPOINT ["tini", "--", "entrypoint.sh"]
