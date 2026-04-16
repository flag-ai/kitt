package middleware

import (
	"crypto/subtle"
	"net/http"
	"strings"
)

// Auth returns middleware that requires a bearer token matching the
// configured admin token on the Authorization header. Returns 401 on
// missing or malformed headers and on mismatched tokens.
//
// The comparison uses crypto/subtle.ConstantTimeCompare to avoid
// leaking information via timing side-channels.
func Auth(token string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			header := r.Header.Get("Authorization")
			if header == "" {
				writeUnauthorized(w, "missing Authorization header")
				return
			}

			const prefix = "Bearer "
			if !strings.HasPrefix(header, prefix) {
				writeUnauthorized(w, "malformed Authorization header")
				return
			}

			provided := strings.TrimPrefix(header, prefix)
			expected := token
			if len(provided) != len(expected) ||
				subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
				writeUnauthorized(w, "invalid token")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

func writeUnauthorized(w http.ResponseWriter, msg string) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("WWW-Authenticate", `Bearer realm="kitt"`)
	w.WriteHeader(http.StatusUnauthorized)
	_, _ = w.Write([]byte(`{"error":"` + msg + `"}`))
}
