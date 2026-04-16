package service

import (
	"context"
	"time"

	"github.com/flag-ai/commons/bonnie"

	"github.com/flag-ai/kitt/internal/db/sqlc"
)

// bonnieStore adapts KITT's sqlc queries to the bonnie.RegistryStore
// contract so the shared flag-commons registry can persist agent state
// without knowing about the KITT schema.
type bonnieStore struct {
	queries *sqlc.Queries
}

// NewBonnieRegistryStore returns a bonnie.RegistryStore backed by the
// kitt_bonnie_agents table.
func NewBonnieRegistryStore(q *sqlc.Queries) bonnie.RegistryStore {
	return &bonnieStore{queries: q}
}

// List returns every agent known to the database.
func (s *bonnieStore) List(ctx context.Context) ([]bonnie.Agent, error) {
	rows, err := s.queries.ListBonnieAgents(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]bonnie.Agent, 0, len(rows))
	for i := range rows {
		r := rows[i]
		out = append(out, bonnie.Agent{
			ID:         fromPgUUID(r.ID).String(),
			Name:       r.Name,
			URL:        r.Url,
			Token:      r.Token,
			Status:     r.Status,
			LastSeenAt: timeFromPgTimestamptz(r.LastSeenAt),
		})
	}
	return out, nil
}

// UpdateStatus writes the latest health-check result back to the
// database.
func (s *bonnieStore) UpdateStatus(ctx context.Context, id, status string, lastSeenAt time.Time) error {
	uid, err := parseUUIDString(id)
	if err != nil {
		return err
	}
	return s.queries.UpdateBonnieAgentStatus(ctx, sqlc.UpdateBonnieAgentStatusParams{
		ID:         toPgUUID(uid),
		Status:     status,
		LastSeenAt: pgTimestamptz(lastSeenAt),
	})
}
