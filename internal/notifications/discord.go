package notifications

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

// DiscordChannel delivers events to a Discord webhook.
type DiscordChannel struct {
	webhookURL string
	http       *http.Client
}

// NewDiscordChannel constructs a DiscordChannel.
func NewDiscordChannel(webhookURL string, httpClient *http.Client) *DiscordChannel {
	if httpClient == nil {
		httpClient = http.DefaultClient
	}
	return &DiscordChannel{webhookURL: webhookURL, http: httpClient}
}

// Name returns the channel identifier.
func (c *DiscordChannel) Name() string { return "discord" }

// discordPayload is a minimal Discord webhook body. We include
// `content` (plaintext rendered) plus a single embed with the event
// kind so receivers can filter by colored bar.
type discordPayload struct {
	Content string         `json:"content"`
	Embeds  []discordEmbed `json:"embeds,omitempty"`
}

type discordEmbed struct {
	Title       string              `json:"title,omitempty"`
	Description string              `json:"description,omitempty"`
	Color       int                 `json:"color,omitempty"`
	Fields      []discordEmbedField `json:"fields,omitempty"`
	URL         string              `json:"url,omitempty"`
}

type discordEmbedField struct {
	Name   string `json:"name"`
	Value  string `json:"value"`
	Inline bool   `json:"inline,omitempty"`
}

// Catppuccin Mocha palette hex values expressed as 0xRRGGBB ints so
// Discord renders the embed bar in a color operators recognize.
const (
	colorGreen = 0xa6e3a1 // success
	colorPeach = 0xfab387 // warning
	colorRed   = 0xf38ba8 // error
	colorBlue  = 0x89b4fa // informational
)

func embedColor(kind EventKind) int {
	switch kind {
	case EventCampaignStarted:
		return colorBlue
	case EventCampaignFinished:
		return colorGreen
	case EventCampaignFailed:
		return colorRed
	case EventBenchmarkFailed:
		return colorPeach
	default:
		return colorBlue
	}
}

// Send posts event to the Discord webhook.
func (c *DiscordChannel) Send(ctx context.Context, event *Event) error {
	if c.webhookURL == "" {
		return fmt.Errorf("discord: webhook URL is empty")
	}
	embed := discordEmbed{
		Title:       event.Title,
		Description: event.Message,
		Color:       embedColor(event.Kind),
		URL:         event.Link,
	}
	for k, v := range event.Fields {
		embed.Fields = append(embed.Fields, discordEmbedField{Name: k, Value: v, Inline: true})
	}
	payload := discordPayload{
		Content: "[KITT] " + string(event.Kind),
		Embeds:  []discordEmbed{embed},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("discord: marshal: %w", err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.webhookURL, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("discord: build request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return fmt.Errorf("discord: do: %w", err)
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("discord: status %d: %s", resp.StatusCode, raw)
	}
	return nil
}
