package handlers

import (
	"io"
	"log/slog"
	"net/http"
	"time"
)

// QuickTestHandler serves /api/v1/quicktest/{run_id}/logs. The actual
// quicktest launch endpoint (POST /quicktest) is wired into the
// campaign runner in a later PR; for now we provide the log stream so
// the UI can be developed against a real SSE endpoint.
type QuickTestHandler struct {
	logger *slog.Logger
}

// NewQuickTestHandler constructs a QuickTestHandler.
func NewQuickTestHandler(logger *slog.Logger) *QuickTestHandler {
	return &QuickTestHandler{logger: logger}
}

// Logs handles GET /api/v1/quicktest/{run_id}/logs. Emits a stream of
// SSE frames; the initial implementation ships keep-alive pings and
// will pipe real agent log lines once PR F+ wires up the bonnie.Client
// log streamer.
//
// We enforce a 10-minute ceiling so idle clients don't hold a
// connection open indefinitely.
func (h *QuickTestHandler) Logs(w http.ResponseWriter, r *http.Request) {
	id, err := parseUUID(r)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid run_id")
		return
	}

	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming not supported")
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	// Emit an initial "subscribed" frame so clients know the stream is
	// active even before any log lines arrive. id came from
	// uuid.Parse, so its string form is strictly hex + hyphens — no
	// XSS possible, but gosec's taint analysis needs an explicit
	// annotation.
	// #nosec G705 -- id is a parsed UUID; characters restricted to [0-9a-f-].
	_, _ = io.WriteString(w, "data: subscribed run_id="+id.String()+"\n\n")
	flusher.Flush()

	ping := time.NewTicker(30 * time.Second)
	defer ping.Stop()
	deadline := time.After(10 * time.Minute)

	for {
		select {
		case <-r.Context().Done():
			return
		case <-deadline:
			_, _ = io.WriteString(w, "event: close\ndata: max duration reached\n\n")
			flusher.Flush()
			return
		case <-ping.C:
			_, _ = io.WriteString(w, ": ping\n\n")
			flusher.Flush()
		}
	}
}
