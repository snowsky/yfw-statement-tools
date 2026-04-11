FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
ARG VITE_MODE=standalone
ENV VITE_MODE=${VITE_MODE}
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
# nginx docker image runs envsubst on /etc/nginx/templates/*.template at startup
# BACKEND_HOST defaults to "backend" (standalone mode); override in sidecar mode.
ENV BACKEND_HOST=backend
