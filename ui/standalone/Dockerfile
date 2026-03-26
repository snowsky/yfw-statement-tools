FROM node:20-alpine AS builder

WORKDIR /app

COPY ui/standalone/package.json ui/standalone/package-lock.json* ./

RUN npm ci

# Copy full ui/ so @shared alias resolves correctly
COPY ui/ ./ui/

WORKDIR /app/ui/standalone
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/ui/standalone/dist /usr/share/nginx/html
COPY ui/standalone/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
