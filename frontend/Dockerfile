# Stage 1: build
FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: serve static files with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Forward /api and /ws to backend — backend URL injected at runtime via env
# For dev, override NGINX_BACKEND_URL; compose proxy handles routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
