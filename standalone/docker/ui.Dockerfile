FROM node:20-alpine AS builder

WORKDIR /app

COPY standalone/ui/package.json standalone/ui/package-lock.json* /app/standalone/ui/

WORKDIR /app/standalone/ui
RUN npm install

WORKDIR /app
COPY standalone/ui/ ./standalone/ui/
COPY shared/ui/ ./standalone/ui/shared/

WORKDIR /app/standalone/ui
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/standalone/ui/dist /usr/share/nginx/html
COPY standalone/docker/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
