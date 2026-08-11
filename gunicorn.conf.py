"""Conservative Gunicorn settings for Flask-SocketIO's threaded worker."""

import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
worker_class = "gthread"
# Gunicorn's built-in balancer is not sticky. Flask-SocketIO therefore requires
# one worker per instance; scale with multiple instances behind a sticky proxy.
workers = 1
threads = int(os.getenv("PEERXIV_GUNICORN_THREADS", "16"))
timeout = int(os.getenv("PEERXIV_GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("PEERXIV_GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("PEERXIV_GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
capture_output = True
worker_tmp_dir = "/dev/shm"
