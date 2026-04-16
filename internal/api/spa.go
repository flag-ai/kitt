package api

import (
	"io/fs"
	"net/http"
	"strings"
)

// SPAHandler serves the embedded SPA files, falling back to
// index.html for unmatched routes so client-side routing works.
// Returns 404 if spaFS is nil — callers should check before
// registering if the SPA is optional.
func SPAHandler(spaFS fs.FS) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if spaFS == nil {
			http.NotFound(w, r)
			return
		}

		path := strings.TrimPrefix(r.URL.Path, "/")
		if path == "" {
			path = "index.html"
		}

		// Probe the requested file — fall back to index.html when it
		// isn't a real asset, so deep-linked routes like /engines load
		// the SPA shell.
		f, err := spaFS.Open(path)
		if err != nil {
			path = "index.html"
		} else {
			_ = f.Close()
		}

		http.ServeFileFS(w, r, spaFS, path)
	}
}
