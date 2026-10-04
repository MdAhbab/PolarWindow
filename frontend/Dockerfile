# syntax=docker/dockerfile:1

# The dashboard as static files behind nginx, which also passes /api/ and /healthz
# on to the api service: one origin, so the browser needs no CORS allowance.

FROM node:24-alpine AS build
WORKDIR /web

# Dependencies first, so a source change does not reinstall every package.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

COPY . .
# Where the built pages ask for the API. A path, not a host: the same server answers both.
ARG VITE_API_BASE=/api/v1
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
