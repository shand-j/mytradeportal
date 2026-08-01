# syntax=docker/dockerfile:1

# -----------------------------------------------------------------------------
# Base stage: install dependencies
# -----------------------------------------------------------------------------
FROM node:22-alpine AS base
WORKDIR /app

RUN corepack enable && corepack prepare pnpm@10.13.1 --activate

COPY package.json pnpm-lock.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

# -----------------------------------------------------------------------------
# Development stage: hot-reload Vite dev server
# -----------------------------------------------------------------------------
FROM base AS development

ENV NODE_ENV=development

COPY . .

EXPOSE 3000

CMD ["pnpm", "dev", "--host"]

# -----------------------------------------------------------------------------
# Production stage: build static assets and serve with Nginx
# -----------------------------------------------------------------------------
FROM base AS production-build

ENV NODE_ENV=production

# Baked into the Vite bundle at build time; on Railway this is passed as a
# build argument pointing at the API service's public domain.
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY . .
RUN pnpm build

FROM nginx:alpine AS production

COPY --from=production-build /app/dist /usr/share/nginx/html
# The nginx image entrypoint runs envsubst over /etc/nginx/templates/*.template
# into /etc/nginx/conf.d/, so ${PORT} in nginx.conf is resolved at container
# start. Railway injects $PORT; default to 80 locally.
COPY nginx.conf /etc/nginx/templates/default.conf.template

ENV PORT=80
ENV API_UPSTREAM_URL=http://api:8000
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
