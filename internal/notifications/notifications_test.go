package notifications

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"
)

func quietLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

type recordingChannel struct {
	events []*Event
	err    error
}

func (r *recordingChannel) Name() string { return "recording" }

func (r *recordingChannel) Send(_ context.Context, e *Event) error {
	r.events = append(r.events, e)
	return r.err
}

func TestNotifier_FansOut(t *testing.T) {
	a := &recordingChannel{}
	b := &recordingChannel{}
	n := NewNotifier(quietLogger(), a, b)

	n.Send(context.Background(), &Event{Kind: EventCampaignStarted, Title: "t"})

	if len(a.events) != 1 || len(b.events) != 1 {
		t.Fatalf("expected one event per channel, got a=%d b=%d", len(a.events), len(b.events))
	}
}

func TestNotifier_ErrorDoesNotStopOthers(t *testing.T) {
	a := &recordingChannel{err: errors.New("boom")}
	b := &recordingChannel{}
	n := NewNotifier(quietLogger(), a, b)

	n.Send(context.Background(), &Event{Kind: EventCampaignStarted})
	if len(b.events) != 1 {
		t.Fatalf("b should still receive events, got %d", len(b.events))
	}
}

func TestSlackChannel_PostsBody(t *testing.T) {
	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Errorf("decode: %v", err)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()
	c := NewSlackChannel(srv.URL, nil)
	if err := c.Send(context.Background(), &Event{Kind: EventCampaignStarted, Title: "T"}); err != nil {
		t.Fatalf("send: %v", err)
	}
	if got["text"] == "" {
		t.Fatal("expected text field")
	}
}

func TestDiscordChannel_PostsEmbed(t *testing.T) {
	var got discordPayload
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&got); err != nil {
			t.Errorf("decode: %v", err)
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	defer srv.Close()
	c := NewDiscordChannel(srv.URL, nil)
	if err := c.Send(context.Background(), &Event{Kind: EventCampaignFinished, Title: "T", Message: "m"}); err != nil {
		t.Fatalf("send: %v", err)
	}
	if len(got.Embeds) != 1 {
		t.Fatalf("expected one embed, got %d", len(got.Embeds))
	}
	if got.Embeds[0].Color != colorGreen {
		t.Fatalf("expected green embed, got %x", got.Embeds[0].Color)
	}
}
