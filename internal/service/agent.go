package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/flag-ai/commons/bonnie"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/flag-ai/kitt/internal/db/sqlc"
	"github.com/flag-ai/kitt/internal/models"
)

// ErrNotFound is returned when a lookup succeeds but the row is absent.
var ErrNotFound = errors.New("not found")

// AgentServicer is implemented by the concrete AgentService; handlers
// depend on the interface so they can be replaced with test doubles.
type AgentServicer interface {
	List(ctx context.Context) ([]models.Agent, error)
	Get(ctx context.Context, id uuid.UUID) (models.Agent, error)
	Create(ctx context.Context, name, url, token string) (models.Agent, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// AgentService persists BONNIE agent rows and keeps the in-memory
// registry in sync.
type AgentService struct {
	queries  *sqlc.Queries
	registry *bonnie.Registry
	logger   *slog.Logger
}

// NewAgentService constructs an AgentService.
func NewAgentService(q *sqlc.Queries, r *bonnie.Registry, logger *slog.Logger) *AgentService {
	return &AgentService{queries: q, registry: r, logger: logger}
}

// List returns every agent.
func (s *AgentService) List(ctx context.Context) ([]models.Agent, error) {
	rows, err := s.queries.ListBonnieAgents(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]models.Agent, 0, len(rows))
	for i := range rows {
		out = append(out, agentFromRow(rows[i]))
	}
	return out, nil
}

// Get returns a single agent by id, or ErrNotFound.
func (s *AgentService) Get(ctx context.Context, id uuid.UUID) (models.Agent, error) {
	row, err := s.queries.GetBonnieAgent(ctx, toPgUUID(id))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.Agent{}, ErrNotFound
		}
		return models.Agent{}, err
	}
	return agentFromRow(row), nil
}

// Create inserts a new agent and immediately upserts it into the
// registry so it's available before the next poll tick.
func (s *AgentService) Create(ctx context.Context, name, url, token string) (models.Agent, error) {
	if name == "" || url == "" {
		return models.Agent{}, fmt.Errorf("agent: name and url are required")
	}
	row, err := s.queries.CreateBonnieAgent(ctx, sqlc.CreateBonnieAgentParams{
		Name:   name,
		Url:    url,
		Token:  token,
		Status: string(models.AgentStatusOffline),
	})
	if err != nil {
		return models.Agent{}, err
	}
	a := agentFromRow(row)
	if s.registry != nil {
		s.registry.Upsert(bonnie.Agent{
			ID:     a.ID.String(),
			Name:   a.Name,
			URL:    a.URL,
			Token:  a.Token,
			Status: string(a.Status),
		})
	}
	s.logger.Info("agent created", "id", a.ID, "name", a.Name, "url", a.URL)
	return a, nil
}

// Delete removes an agent by id and evicts it from the registry.
func (s *AgentService) Delete(ctx context.Context, id uuid.UUID) error {
	if err := s.queries.DeleteBonnieAgent(ctx, toPgUUID(id)); err != nil {
		return err
	}
	if s.registry != nil {
		s.registry.Remove(id.String())
	}
	s.logger.Info("agent deleted", "id", id)
	return nil
}

// agentFromRow converts a sqlc.KittBonnieAgent to a models.Agent.
func agentFromRow(row sqlc.KittBonnieAgent) models.Agent { //nolint:gocritic // value receiver for clean conversion API
	return models.Agent{
		ID:         fromPgUUID(row.ID),
		Name:       row.Name,
		URL:        row.Url,
		Token:      row.Token,
		Status:     models.AgentStatus(row.Status),
		LastSeenAt: timePtrFromPgTimestamptz(row.LastSeenAt),
		CreatedAt:  timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:  timeFromPgTimestamptz(row.UpdatedAt),
	}
}
