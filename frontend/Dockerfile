# Two stages:
#   build - Node turns the React code into plain HTML, CSS and JS files
#   final - nginx serves those files and forwards /api to the backend
# Node is only used while building; the final image contains no Node.

FROM node:24.21.0-alpine AS build

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
# "npm ci" installs exactly what package-lock.json lists.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build


FROM nginx:1.31.6-alpine

# HTTP server + shared settings; the HTTPS server is kept aside and only
# switched on at start-up by enable-https.sh when a certificate exists.
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/app.conf /etc/nginx/app.conf
COPY nginx/https.conf /etc/nginx/optional/https.conf
COPY nginx/enable-https.sh /docker-entrypoint.d/40-enable-https.sh
RUN chmod +x /docker-entrypoint.d/40-enable-https.sh

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80 443
