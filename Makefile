.PHONY: help build up down restart logs ps exec

# Default target
help:
	@echo "Available commands:"
	@echo "  make build    - Build the docker image"
	@echo "  make up       - Start the container in background"
	@echo "  make down     - Stop and remove the container"
	@echo "  make restart  - Restart the container"
	@echo "  make logs     - View container logs"
	@echo "  make ps       - List running containers"
	@echo "  make exec     - Access the container shell"

# Docker Compose commands
build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f ai-service

ps:
	docker compose ps

exec:
	docker compose exec ai-service /bin/bash || docker compose exec ai-service sh

recreate:
	docker compose up -d --build --force-recreate