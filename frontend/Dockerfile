ARG NODE_IMAGE=docker.io/library/node:24.21.0-alpine3.23
ARG NGINX_IMAGE=docker.io/library/nginx:1.30-alpine

FROM ${NODE_IMAGE} AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY frontend/package.json ./frontend/package.json
RUN pnpm install --frozen-lockfile --filter @pandawords/frontend
COPY frontend ./frontend
RUN pnpm --filter @pandawords/frontend build

FROM ${NGINX_IMAGE} AS runtime
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html
EXPOSE 80
