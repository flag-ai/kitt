// Package notifications delivers benchmark and campaign events to
// external chat channels (Slack + Discord). The package is a small
// fanout: a Notifier holds a slice of Channel implementations, and
// dispatch iterates them — each channel decides whether to accept the
// event based on its configured event filters.
//
// Events are best-effort: a failure in one channel is logged but does
// not prevent delivery to the others, and never fails the caller
// (campaigns and quicktests should not block on notification
// availability).
package notifications

import (
	"context"
	"log/slog"
	"sync"
	"time"
)

// EventKind is the type of notification.
type EventKind string

// Supported notification event kinds.
const (
	EventCampaignStarted  EventKind = "campaign.started"
	EventCampaignFinished EventKind = "campaign.finished"
	EventCampaignFailed   EventKind = "campaign.failed"
	EventBenchmarkFailed  EventKind = "benchmark.failed"
)

// Event is the payload dispatched to every registered Channel.
type Event struct {
	Kind      EventKind
	Title     string
	Message   string
	Link      string
	Timestamp time.Time
	// Fields is a free-form map serialized into channel-native
	// structured layouts (Slack blocks / Discord embeds) when the
	// channel supports them.
	Fields map[string]string
}

// Channel is a single delivery destination — typically a webhook.
type Channel interface {
	// Name returns a short identifier used in logs.
	Name() string
	// Send delivers event. Implementations must honor ctx and return
	// an error on transport failure; partial delivery is not a
	// supported concept at this layer.
	Send(ctx context.Context, event *Event) error
}

// Notifier fans events out to every configured Channel.
type Notifier struct {
	channels []Channel
	logger   *slog.Logger
}

// NewNotifier constructs a Notifier. Passing zero channels is valid —
// every Send becomes a logged no-op.
func NewNotifier(logger *slog.Logger, channels ...Channel) *Notifier {
	return &Notifier{channels: channels, logger: logger}
}

// perChannelTimeout is the maximum time a single channel send may take
// before being cancelled.
const perChannelTimeout = 10 * time.Second

// Send dispatches event to every registered channel in parallel,
// returning once all have completed or timed out. Each channel gets
// its own 10-second context so a slow webhook cannot starve the rest.
// Errors are logged; callers never see them because notifications are
// best-effort.
func (n *Notifier) Send(ctx context.Context, event *Event) {
	if len(n.channels) == 0 {
		return
	}
	if event.Timestamp.IsZero() {
		event.Timestamp = time.Now().UTC()
	}
	var wg sync.WaitGroup
	for _, ch := range n.channels {
		wg.Add(1)
		go func(ch Channel) {
			defer wg.Done()
			chCtx, cancel := context.WithTimeout(ctx, perChannelTimeout)
			defer cancel()
			if err := ch.Send(chCtx, event); err != nil {
				n.logger.Warn("notifications: send failed",
					"channel", ch.Name(), "kind", event.Kind, "error", err)
			}
		}(ch)
	}
	wg.Wait()
}
