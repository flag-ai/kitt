package handlers

import (
	"log/slog"
	"net/http"
	"time"

	"github.com/flag-ai/kitt/internal/notifications"
)

// NotificationHandler serves /api/v1/notifications.
type NotificationHandler struct {
	notifier *notifications.Notifier
	logger   *slog.Logger
}

// NewNotificationHandler constructs a NotificationHandler.
func NewNotificationHandler(notifier *notifications.Notifier, logger *slog.Logger) *NotificationHandler {
	return &NotificationHandler{notifier: notifier, logger: logger}
}

// testPayload is the JSON body accepted by /notifications/test.
type testPayload struct {
	Title   string            `json:"title"`
	Message string            `json:"message"`
	Fields  map[string]string `json:"fields,omitempty"`
}

// Test handles POST /api/v1/notifications/test. Fires a synthetic
// event through every configured channel and returns 202 — delivery
// failures are logged server-side.
func (h *NotificationHandler) Test(w http.ResponseWriter, r *http.Request) {
	var req testPayload
	if err := decodeBody(w, r, &req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid json body")
		return
	}
	if req.Title == "" {
		req.Title = "KITT test notification"
	}
	if req.Message == "" {
		req.Message = "If you can see this, notifications are wired up correctly."
	}
	event := &notifications.Event{
		Kind:      "test",
		Title:     req.Title,
		Message:   req.Message,
		Fields:    req.Fields,
		Timestamp: time.Now().UTC(),
	}
	h.notifier.Send(r.Context(), event)
	w.WriteHeader(http.StatusAccepted)
}
