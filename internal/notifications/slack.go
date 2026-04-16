package notifications

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

// SlackChannel delivers events to a Slack Incoming Webhook.
type SlackChannel struct {
	webhookURL string
	http       *http.Client
}

// NewSlackChannel constructs a SlackChannel.
func NewSlackChannel(webhookURL string, httpClient *http.Client) *SlackChannel {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	return &SlackChannel{webhookURL: webhookURL, http: httpClient}
}

// Name returns the channel identifier.
func (c *SlackChannel) Name() string { return "slack" }

// slackPayload is the JSON shape Slack accepts. We keep it lean —
// title + message + optional context fields — rather than reaching
// for full Block Kit. Operators can build richer surfaces server-side
// once the rest of the rewrite stabilizes.
type slackPayload struct {
	Text string `json:"text"`
}

// Send posts event to the Slack webhook. The body is a simple
// Markdown-ish blob; Slack renders it faithfully enough for the
// campaign/benchmark notifications KITT emits.
func (c *SlackChannel) Send(ctx context.Context, event *Event) error {
	if c.webhookURL == "" {
		return fmt.Errorf("slack: webhook URL is empty")
	}
	body, err := json.Marshal(slackPayload{Text: renderText(event)})
	if err != nil {
		return fmt.Errorf("slack: marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.webhookURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("slack: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("slack: do: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("slack: status %d: %s", resp.StatusCode, raw)
	}
	return nil
}

// renderText builds a compact Markdown-ish rendering. Used by both
// Slack and Discord channels; the format is portable and operators
// can always swap in a richer renderer later.
func renderText(event *Event) string {
	var b strings.Builder
	b.WriteString("*[KITT]* ")
	b.WriteString(string(event.Kind))
	if event.Title != "" {
		b.WriteString(" — ")
		b.WriteString(event.Title)
	}
	if event.Message != "" {
		b.WriteString("\n")
		b.WriteString(event.Message)
	}
	for k, v := range event.Fields {
		b.WriteString("\n• ")
		b.WriteString(k)
		b.WriteString(": ")
		b.WriteString(v)
	}
	if event.Link != "" {
		b.WriteString("\n<")
		b.WriteString(event.Link)
		b.WriteString(">")
	}
	return b.String()
}
