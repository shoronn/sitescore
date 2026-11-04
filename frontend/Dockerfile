# MAKTECH SiteScore web app: a static React build served by nginx on port 80.
#
# VITE_API_BASE is needed twice:
#   build time  baked into the JavaScript (where the app sends API calls)
#   runtime     written into the Content-Security-Policy header when nginx starts
# In Coolify, add it once and tick "Build Variable"; it is then available at both stages.

FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE=https://api-sitescore.maktechgroup.com
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.28-alpine
ARG VITE_API_BASE=https://api-sitescore.maktechgroup.com
ENV VITE_API_BASE=$VITE_API_BASE \
    NGINX_ENVSUBST_FILTER=^VITE_
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD wget -qO- http://127.0.0.1/healthz >/dev/null || exit 1
