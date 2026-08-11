PYTHON ?= python3
GUNICORN ?= gunicorn
FLASK := $(PYTHON) -m flask

.PHONY: install run test smoke-live release-check migrate migration migration-check reset-dev-db

install:
	$(PYTHON) -m pip install -r requirements-dev.txt
	npm install

run:
	cd client && $(PYTHON) server.py

test:
	$(PYTHON) -m pytest -q
	npm run test:ui

smoke-live:
	PYTHON=$(PYTHON) GUNICORN=$(GUNICORN) scripts/smoke_live.sh

release-check:
	$(PYTHON) -m compileall -q client
	$(PYTHON) -m pytest -W error --cov=client --cov-report=term-missing -q
	$(PYTHON) -m pip_audit -r requirements.txt --progress-spinner off --cache-dir /tmp/peerxiv-pip-audit-cache
	npm audit --cache /tmp/peerxiv-npm-cache
	npm run build
	npm run test:ui
	cd client && $(FLASK) --app server db check
	$(MAKE) smoke-live

migrate:
	cd client && $(FLASK) --app server db upgrade

migration:
	@test -n "$(name)" || (echo "usage: make migration name='describe change'" && exit 1)
	cd client && $(FLASK) --app server db migrate -m "$(name)"

migration-check:
	cd client && $(FLASK) --app server db check

reset-dev-db:
	PYTHON=$(PYTHON) scripts/reset_dev_db.sh
