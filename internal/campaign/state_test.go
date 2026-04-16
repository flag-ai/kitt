package campaign

import (
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/models"
)

func TestState_SetGet(t *testing.T) {
	s := NewState()
	id := uuid.New()
	s.Set(&models.CampaignRunStatus{CampaignID: id, State: "running"})

	got, ok := s.Get(id)
	if !ok {
		t.Fatal("Get returned not found")
	}
	if got.State != "running" {
		t.Fatalf("state = %q", got.State)
	}
}

func TestState_SubscribeDeliversUpdates(t *testing.T) {
	s := NewState()
	id := uuid.New()
	ch, cancel := s.Subscribe(id)
	defer cancel()

	s.Set(&models.CampaignRunStatus{CampaignID: id, State: "queued"})
	s.Set(&models.CampaignRunStatus{CampaignID: id, State: "running"})

	seen := make([]string, 0, 2)
	timeout := time.After(500 * time.Millisecond)
	for len(seen) < 2 {
		select {
		case st, ok := <-ch:
			if !ok {
				t.Fatalf("channel closed early, got %v", seen)
			}
			seen = append(seen, st.State)
		case <-timeout:
			t.Fatalf("timeout waiting for updates, got %v", seen)
		}
	}
	if seen[0] != "queued" || seen[1] != "running" {
		t.Fatalf("events = %v", seen)
	}
}

func TestState_CancelUnsubscribes(t *testing.T) {
	s := NewState()
	id := uuid.New()
	ch, cancel := s.Subscribe(id)
	cancel()
	_, ok := <-ch
	if ok {
		t.Fatal("expected channel closed after cancel")
	}
}
