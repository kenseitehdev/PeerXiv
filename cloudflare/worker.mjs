import { Container } from "@cloudflare/containers";

const FORWARDED_ENVIRONMENT = [
  "DATABASE_URL",
  "REDIS_URL",
  "SOCKETIO_ASYNC_MODE",
  "SOCKETIO_CHANNEL",
  "PEERXIV_SECRET_KEY",
  "PEERXIV_TRUSTED_HOSTS",
  "PEERXIV_FRONTEND_ORIGINS",
  "PEERXIV_REGISTRATION_MODE",
  "PEERXIV_ALPHA_INVITE_CODE",
  "PEERXIV_ALLOW_SQLITE_PRODUCTION",
  "PEERXIV_MANUSCRIPT_STORAGE_ROOT",
  "PEERXIV_MANUSCRIPT_REDIRECT_HOSTS",
  "PEERXIV_MAX_MANUSCRIPT_BYTES",
  "PEERXIV_MAX_MANUSCRIPT_PAGES",
  "PEERXIV_CLAMAV_HOST",
  "PEERXIV_CLAMAV_PORT",
  "PEERXIV_CLAMAV_TIMEOUT",
  "PEERXIV_MALWARE_SCAN_REQUIRED",
  "PEERXIV_CREDENTIAL_ENCRYPTION_KEY",
  "PEERXIV_ORCID_CLIENT_ID",
  "PEERXIV_ORCID_CLIENT_SECRET",
  "PEERXIV_ORCID_ENVIRONMENT",
  "PEERXIV_ORCID_REDIRECT_URI",
  "PEERXIV_ORCID_TIMEOUT",
  "PEERXIV_ZENODO_ENVIRONMENT",
  "PEERXIV_ZENODO_ALLOW_PRODUCTION_PUBLISH",
  "PEERXIV_ZENODO_TIMEOUT",
  "PEERXIV_RATELIMIT_STORAGE_URI",
  "PEERXIV_RATELIMIT_KEY_PREFIX",
  "PEERXIV_GUNICORN_THREADS",
  "PEERXIV_GUNICORN_TIMEOUT",
  "PEERXIV_GUNICORN_GRACEFUL_TIMEOUT",
  "PEERXIV_GUNICORN_KEEPALIVE",
  "PEERXIV_GUNICORN_WORKER_TMP_DIR",
  "PEERXIV_RUN_MIGRATIONS",
];

function containerEnvironment(workerEnvironment, request) {
  const values = {
    PEERXIV_ENV: "production",
    PEERXIV_HOST: "0.0.0.0",
    PEERXIV_PORT: "8000",
    PORT: "8000",
    PEERXIV_PROXY_FIX: "1",
    PEERXIV_PROXY_X_FOR: "1",
    PEERXIV_PROXY_X_PROTO: "1",
    PEERXIV_PROXY_X_HOST: "1",
    PEERXIV_PROXY_X_PORT: "1",
    PEERXIV_PROXY_X_PREFIX: "0",
  };

  for (const name of FORWARDED_ENVIRONMENT) {
    const value = workerEnvironment[name];
    if (typeof value === "string" && value.length > 0) {
      values[name] = value;
    }
  }

  const publicUrl = new URL(request.url);
  values.PEERXIV_TRUSTED_HOSTS ??= publicUrl.hostname;
  values.PEERXIV_FRONTEND_ORIGINS ??= publicUrl.origin;
  return values;
}

export class PeerXivContainer extends Container {
  defaultPort = 8000;
  requiredPorts = [8000];
  sleepAfter = "30m";
}

export default {
  async fetch(request, env) {
    const container = env.PEERXIV_CONTAINER.getByName("primary");

    await container.startAndWaitForPorts({
      ports: 8000,
      cancellationOptions: {
        abort: request.signal,
        instanceGetTimeoutMS: 120_000,
        portReadyTimeoutMS: 120_000,
      },
      startOptions: {
        enableInternet: true,
        envVars: containerEnvironment(env, request),
      },
    });

    // Container.fetch() preserves WebSocket upgrades used by Flask-SocketIO.
    return container.fetch(request);
  },
};
