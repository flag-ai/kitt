package handlers

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

// errorResponse is the standard error envelope returned by KITT.
//
//nolint:unused // used by handlers introduced in PR B onwards.
type errorResponse struct {
	Error string `json:"error"`
}

// writeJSON encodes v as JSON with the given status code.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError writes a JSON error response.
//
//nolint:unused // used by handlers introduced in PR B onwards.
func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, errorResponse{Error: msg})
}

// parseUUID extracts and parses the "id" URL parameter.
//
//nolint:unused // used by handlers introduced in PR B onwards.
func parseUUID(r *http.Request) (uuid.UUID, error) {
	raw := chi.URLParam(r, "id")
	return uuid.Parse(raw)
}

// maxBodySize is the maximum allowed request body size (1 MiB). Larger
// payloads are rejected to prevent memory exhaustion.
//
//nolint:unused // used by handlers introduced in PR B onwards.
const maxBodySize = 1 << 20

// decodeBody decodes the JSON request body into dst.
//
//nolint:unused // used by handlers introduced in PR B onwards.
func decodeBody(w http.ResponseWriter, r *http.Request, dst any) error {
	r.Body = http.MaxBytesReader(w, r.Body, maxBodySize)
	defer func() { _ = r.Body.Close() }()
	return json.NewDecoder(r.Body).Decode(dst)
}
