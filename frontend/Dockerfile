ARG NODE_IMAGE=node:lts-alpine
FROM ${NODE_IMAGE} AS builder
WORKDIR /app

COPY package*.json ./
RUN node --version && npm --version && npm ci

COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
