FROM node:20-alpine AS build

WORKDIR /src/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine

ARG BUILD_REVISION=unknown

LABEL org.opencontainers.image.source="https://github.com/Zent7/vova-medcenter" \
      org.opencontainers.image.revision="${BUILD_REVISION}"

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/frontend/dist /usr/share/nginx/html
RUN printf '{"build_revision":"%s"}\n' "$BUILD_REVISION" > /usr/share/nginx/html/build.json

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=6 \
    CMD wget -qO- http://127.0.0.1/build.json >/dev/null || exit 1

