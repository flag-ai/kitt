# Stage 1: Build Go binary.
# The React SPA arrives in PR I with a second web-builder stage; for
# now the server is API-only.
FROM golang:1.25-alpine AS go-builder
RUN apk add --no-cache gcc musl-dev
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown
RUN CGO_ENABLED=0 go build -ldflags "\
  -X github.com/flag-ai/commons/version.Version=${VERSION} \
  -X github.com/flag-ai/commons/version.Commit=${COMMIT} \
  -X github.com/flag-ai/commons/version.Date=${BUILD_DATE}" \
  -o /kitt ./cmd/kitt

# Stage 2: Final image.
FROM alpine:3.21
RUN apk add --no-cache ca-certificates tzdata
COPY --from=go-builder /kitt /usr/local/bin/kitt
COPY --from=go-builder /app/migrations /migrations
EXPOSE 8080
ENTRYPOINT ["kitt"]
CMD ["serve"]
