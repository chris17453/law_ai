.PHONY: help setup start stop restart clean ingest search search-region search-region-only status stats regions logs shell test db-backup db-restore

# Default target
help:
	@echo "Georgia Law AI - Available Commands:"
	@echo ""
	@echo "  Setup & Installation:"
	@echo "    make setup          - Install dependencies and initialize database"
	@echo "    make start          - Start Qdrant vector database"
	@echo "    make stop           - Stop all services"
	@echo "    make restart        - Restart all services"
	@echo ""
	@echo "  Data Management (Two-Pass Process):"
	@echo "    make ingest-docs    - Pass 1: Load documents into PostgreSQL (fast)"
	@echo "    make generate-embeddings - Pass 2: Generate vector embeddings (slower)"
	@echo "    make ingest         - Run both passes (load docs + embeddings)"
	@echo "    make ingest-ga-code - Ingest only Georgia Code"
	@echo "    make ingest-cases   - Ingest only CourtListener cases"
	@echo "    make ingest-ordinances - Ingest only Gwinnett ordinances"
	@echo ""
	@echo "  Search & Query:"
	@echo "    make search QUERY='your query' - Search the database"
	@echo "    make search-ga QUERY='...'      - Search only GA Code"
	@echo "    make search-cases QUERY='...'   - Search only case law"
	@echo "    make search-region QUERY='...' REGION='...' - Search by region (e.g., GA-ATLANTA)"
	@echo "    make search-region-only QUERY='...' REGION='...' - Search exact region only"
	@echo ""
	@echo "  Monitoring & Maintenance:"
	@echo "    make status         - Show service status"
	@echo "    make stats          - Show database statistics"
	@echo "    make regions        - List all available regions/jurisdictions"
	@echo "    make logs           - Show Qdrant logs"
	@echo "    make shell          - Open Python shell with env loaded"
	@echo "    make clean          - Remove all data and containers"
	@echo "    make clean-data     - Remove only vector database data"
	@echo ""
	@echo "  Database Backup & Restore:"
	@echo "    make db-backup            - Create database backup (default: ./data/db_backups)"
	@echo "    make db-restore DIR=path  - Restore database from backup chunks"
	@echo ""
	@echo "  Development:"
	@echo "    make test           - Run tests"
	@echo "    make lint           - Run linters"
	@echo ""

# Setup: Install dependencies and initialize
setup:
	@echo "Setting up Law AI environment..."
	uv sync
	@echo "Starting PostgreSQL..."
	docker compose up -d
	@echo "Waiting for PostgreSQL to be ready..."
	@sleep 8
	@echo "Initializing database..."
	uv run python scripts/init_db.py
	@echo "✓ Setup complete!"

# Docker management
start:
	@echo "Starting services..."
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 3
	@echo "✓ Services started"
	@make status

stop:
	@echo "Stopping services..."
	docker compose down
	@echo "✓ Services stopped"

restart:
	@make stop
	@make start

# Data ingestion (two-pass process)
ingest-docs:
	@echo "Pass 1: Loading documents into PostgreSQL (fast, no embeddings)..."
	uv run python scripts/ingest.py --all --verbose
	@echo ""
	@echo "✓ Documents loaded! Run 'make generate-embeddings' to create vector embeddings."

generate-embeddings:
	@echo "Pass 2: Generating embeddings with Azure OpenAI..."
	@echo "This may take 30-45 minutes depending on API rate limits"
	uv run python scripts/generate_embeddings.py --all
	@make stats

ingest: ingest-docs generate-embeddings
	@echo "✓ Complete ingestion finished (documents + embeddings)"

ingest-ga-code:
	@echo "Ingesting Georgia Code (documents only)..."
	uv run python scripts/ingest.py --source data/ga_code.jsonl --source-type GA_CODE

ingest-cases:
	@echo "Ingesting CourtListener cases (documents only)..."
	uv run python scripts/ingest.py --source data/courtlistener_ga.jsonl --source-type COURTLISTENER

ingest-ordinances:
	@echo "Ingesting Gwinnett ordinances (documents only)..."
	uv run python scripts/ingest.py --source data/municode_gwinnett.jsonl --source-type MUNICODE

# Search
search:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make search QUERY='your search query'"; \
		exit 1; \
	fi
	@uv run python scripts/search.py "$(QUERY)"

search-ga:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make search-ga QUERY='your search query'"; \
		exit 1; \
	fi
	@uv run python scripts/search.py "$(QUERY)" --source GA_CODE

search-cases:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make search-cases QUERY='your search query'"; \
		exit 1; \
	fi
	@uv run python scripts/search.py "$(QUERY)" --source COURTLISTENER

search-region:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make search-region QUERY='your query' REGION='region-id'"; \
		echo "Example: make search-region QUERY='noise ordinance' REGION='GA-ATLANTA'"; \
		echo ""; \
		echo "Common region IDs:"; \
		echo "  GA              - Georgia (state)"; \
		echo "  GA-FULTON       - Fulton County"; \
		echo "  GA-GWINNETT     - Gwinnett County"; \
		echo "  GA-ATLANTA      - Atlanta (includes parent counties and state)"; \
		echo "  GA-LAWRENCEVILLE - Lawrenceville"; \
		exit 1; \
	fi
	@if [ -z "$(REGION)" ]; then \
		echo "Error: REGION is required"; \
		echo "Usage: make search-region QUERY='your query' REGION='region-id'"; \
		exit 1; \
	fi
	@uv run python scripts/search.py "$(QUERY)" --region $(REGION)

search-region-only:
	@if [ -z "$(QUERY)" ]; then \
		echo "Usage: make search-region-only QUERY='your query' REGION='region-id'"; \
		echo "This searches ONLY the specified region (excludes parent jurisdictions)"; \
		exit 1; \
	fi
	@if [ -z "$(REGION)" ]; then \
		echo "Error: REGION is required"; \
		echo "Usage: make search-region-only QUERY='your query' REGION='region-id'"; \
		exit 1; \
	fi
	@uv run python scripts/search.py "$(QUERY)" --region $(REGION) --region-only

# Monitoring
status:
	@echo "Service Status:"
	@docker compose ps
	@echo ""
	@echo "PostgreSQL Connection Test:"
	@docker exec law_ai_postgres pg_isready -U law_ai_user -d law_ai || echo "PostgreSQL not responding"

stats:
	@echo "Database Statistics:"
	@uv run python scripts/stats.py

regions:
	@echo "Available Regions/Jurisdictions:"
	@echo ""
	@docker exec law_ai_postgres psql -U law_ai_user -d law_ai -c \
		"SELECT type, id, name FROM regions ORDER BY type, name" \
		-t | awk '{printf "  %s\n", $$0}'

logs:
	docker compose logs -f postgres

shell:
	@echo "Opening Python shell with environment loaded..."
	uv run python

# Cleanup
clean:
	@echo "WARNING: This will delete ALL data and containers!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker compose down -v; \
		rm -rf qdrant_storage; \
		rm -f law_ai.db; \
		echo "✓ Cleanup complete"; \
	else \
		echo "Cancelled"; \
	fi

clean-data:
	@echo "Removing database data..."
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		rm -rf postgres_data; \
		rm -rf qdrant_storage; \
		rm -f law_ai.db; \
		docker compose restart postgres; \
		echo "✓ Data cleared"; \
	else \
		echo "Cancelled"; \
	fi

# Development
test:
	@echo "Running tests..."
	uv run pytest tests/ -v

lint:
	@echo "Running linters..."
	uv run ruff check .
	uv run black --check .

# Quick start for new users
quickstart: setup
	@echo ""
	@echo "✓ Quick start complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Fetch legal data:       python law_fetch.py --out data --no-verify"
	@echo "  2. Load documents:         make ingest-docs"
	@echo "  3. Generate embeddings:    make generate-embeddings"
	@echo "  4. Search:                 make search QUERY='murder laws in Georgia'"
	@echo ""

# Database backup and restore
db-backup:
	@echo "Creating database backup..."
	uv run lawbot db backup --dir ./data/db_backups
	@echo ""
	@echo "✓ Backup complete! Files stored in ./data/db_backups"
	@echo "To restore: make db-restore DIR=./data/db_backups"

db-restore:
	@if [ -z "$(DIR)" ]; then \
		echo "Usage: make db-restore DIR=path/to/backup"; \
		echo "Example: make db-restore DIR=./data/db_backups"; \
		exit 1; \
	fi
	@echo "Restoring database from: $(DIR)"
	uv run lawbot db restore $(DIR)
