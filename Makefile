PYTHON ?= python3
HOST ?= 127.0.0.1
PORT ?= 8765
JOURNAL ?= journal.log

.PHONY: local server client test lint

local:
	$(PYTHON) -m src.cli local

server:
	$(PYTHON) -m src.cli server --host $(HOST) --port $(PORT) --journal $(JOURNAL)

client:
	$(PYTHON) -m src.cli client --host $(HOST) --port $(PORT)

test:
	$(PYTHON) -m coverage run -m pytest
	$(PYTHON) -m coverage report -m

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
