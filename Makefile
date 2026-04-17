.PHONY: dev test test-integration lint security sqlc build docker docker-up docker-down

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
