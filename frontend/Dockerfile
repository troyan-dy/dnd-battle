# syntax=docker/dockerfile:1
#
# Frontend image: build the Vite SPA, then serve it with nginx. nginx also
# reverse-proxies the API + realtime paths to the backend, so the browser talks
# to a SINGLE origin and the REST API needs no CORS middleware (mirrors the
# same-origin choice already used by the e2e harness).

# --- build stage ---------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# .npmrc pins the public npm registry (not the work Artifactory); copy it so
# `npm ci` resolves the same way inside the container.
COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

# Build the SPA to call the API SAME-ORIGIN. The client normalises a base of "/"
# to "" (.replace(/\/+$/, "")), so every API/Socket.IO call becomes relative and
# is served by nginx on this origin.
ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- runtime stage -------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
