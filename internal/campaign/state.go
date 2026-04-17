// Package campaign contains the campaign runner and in-app scheduler.
//
// The runner is responsible for expanding a CampaignConfig into
// (model × engine × benchmark × agent) runs and dispatching them via
// BONNIE. The scheduler is a thin wrapper around robfig/cron/v3 that
// reloads schedules from the campaigns table on demand.
//
// This package focuses on the control plane. Actual result storage
// lands in PR F (internal/storage).
package campaign

import (
	"sync"

	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/models"
)

// State is the in-memory state map shared between the runner (writer)
// and the SSE status endpoint (reader). It is intentionally simple —
// no persistence — so a server restart forgets in-flight status. The
// persisted runs/benchmarks tables are the source of truth for
// historical data.
type State struct {
	mu       sync.RWMutex
	statuses map[uuid.UUID]models.CampaignRunStatus

	subsMu sync.Mutex
	subs   map[uuid.UUID][]chan models.CampaignRunStatus
}

// NewState constructs an empty State.
func NewState() *State {
	return &State{
		statuses: map[uuid.UUID]models.CampaignRunStatus{},
		subs:     map[uuid.UUID][]chan models.CampaignRunStatus{},
	}
}

// Set replaces the current status for a campaign and notifies every
// subscriber. A slow subscriber will not block the writer — missed
// updates are simply dropped for that subscriber.
func (s *State) Set(status *models.CampaignRunStatus) {
	s.mu.Lock()
	s.statuses[status.CampaignID] = *status
	s.mu.Unlock()
	s.notify(status)
}

// Get returns the current status for id, or (zero, false).
func (s *State) Get(id uuid.UUID) (models.CampaignRunStatus, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	st, ok := s.statuses[id]
	return st, ok
}

// Subscribe registers a channel that receives every subsequent status
// change for id. The returned cancel func unregisters the channel and
// closes it.
func (s *State) Subscribe(id uuid.UUID) (events <-chan models.CampaignRunStatus, cancel func()) {
	ch := make(chan models.CampaignRunStatus, 8)

	s.subsMu.Lock()
	s.subs[id] = append(s.subs[id], ch)
	s.subsMu.Unlock()

	cancel = func() {
		s.subsMu.Lock()
		defer s.subsMu.Unlock()
		subs := s.subs[id]
		for i, c := range subs {
			if c == ch {
				s.subs[id] = append(subs[:i], subs[i+1:]...)
				close(ch)
				return
			}
		}
	}
	return ch, cancel
}

func (s *State) notify(status *models.CampaignRunStatus) {
	s.subsMu.Lock()
	subs := append([]chan models.CampaignRunStatus(nil), s.subs[status.CampaignID]...)
	s.subsMu.Unlock()
	for _, ch := range subs {
		select {
		case ch <- *status:
		default:
			// Drop if the subscriber is behind — prevents a slow
			// consumer from stalling the runner or blocking other
			// subscribers.
		}
	}
}
