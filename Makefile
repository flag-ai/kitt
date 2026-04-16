.PHONY: dev test test-integration lint security sqlc build docker docker-up docker-down smoke-benchmarks

# Development — bring up Postgres so `go run ./cmd/kitt serve` just works.
dev:
	docker compose up -d postgres
	@echo "Postgres started. Run 'go run ./cmd/kitt serve' to start KITT."

# Testing
test:
	go test -race -coverprofile=coverage.out ./...
	@echo "Coverage:"
	@go tool cover -func=coverage.out | tail -1

test-integration:
	go test -race -tags integration ./tests/...

# Code quality
lint:
	golangci-lint run

security:
	gosec ./...

# Code generation
sqlc:
	sqlc generate

# Build
build:
	go build -o kitt ./cmd/kitt

# Docker
docker:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down

# Smoke test every reference benchmark against the stdlib mock engine.
# Installs httpx/pyyaml/jsonschema into a throwaway venv so CI and
# local runs don't depend on a pre-seeded Python environment.
smoke-benchmarks:
	@VENV=$$(mktemp -d)/smoke-venv && \
	python3 -m venv $$VENV && \
	$$VENV/bin/pip install --quiet httpx==0.27.2 pyyaml==6.0.2 jsonschema==4.23.0 && \
	$$VENV/bin/python3 benchmarks-reference/tools/smoke_test.py
