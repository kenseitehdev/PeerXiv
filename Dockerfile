FROM node:24-alpine AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY scripts/build_frontend.mjs scripts/build_frontend.mjs
COPY client/templates/src/tailwind.input.css client/templates/src/tailwind.input.css
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PEERXIV_ENV=production \
    PORT=8000
WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend /build/client/templates/src/tailwind.css /app/client/templates/src/tailwind.css
COPY --from=frontend /build/client/templates/vendor/socket.io.esm.min.js /app/client/templates/vendor/socket.io.esm.min.js
RUN addgroup --system peerxiv \
    && adduser --system --ingroup peerxiv --home /nonexistent peerxiv \
    && mkdir -p /data/manuscripts \
    && chown -R peerxiv:peerxiv /data

USER peerxiv
EXPOSE 8000
ENTRYPOINT ["/app/docker-entrypoint.sh"]
