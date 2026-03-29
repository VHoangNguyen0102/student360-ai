.PHONY: help build up down restart logs ps exec recreate
.PHONY: up-llm build-llm logs-llm pull-model openapi

# Default target
help:
	@echo "Available commands:"
	@echo "  make build    - Build the docker image"
	@echo "  make up       - Start the container in background"
	@echo "  make up-llm   - Start ai-service + ollama (profile local-llm)"
	@echo "  make down     - Stop and remove the container"
	@echo "  make restart  - Restart the container"
	@echo "  make logs     - View container logs"
	@echo "  make logs-llm - View ollama logs"
	@echo "  make ps       - List running containers"
	@echo "  make exec     - Access the container shell"
	@echo "  make pull-model - Pull Ollama model from .env"
	@echo "  make openapi  - Print OpenAPI URL"

# Docker Compose commands
build:
	docker compose build

up:
	docker compose up -d

up-llm:
	docker compose --profile local-llm up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f ai-service

logs-llm:
	docker compose --profile local-llm logs -f ollama

ps:
	docker compose ps

exec:
	docker compose exec ai-service /bin/bash || docker compose exec ai-service sh

recreate:
	docker compose up -d --build --force-recreate

pull-model:
	@echo "Pulling Ollama model from .env (OLLAMA_MODEL)..."
	docker compose --profile local-llm exec ollama ollama pull $$OLLAMA_MODEL

openapi:
	@echo "AI OpenAPI: http://localhost:8001/openapi.json"