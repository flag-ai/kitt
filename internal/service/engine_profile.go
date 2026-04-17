package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/flag-ai/kitt/internal/db/sqlc"
	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/models"
)

// EngineProfileServicer is the interface handlers depend on.
type EngineProfileServicer interface {
	List(ctx context.Context, engine string) ([]models.EngineProfile, error)
	Get(ctx context.Context, id uuid.UUID) (models.EngineProfile, error)
	Create(ctx context.Context, p *models.EngineProfile) (models.EngineProfile, error)
	Update(ctx context.Context, p *models.EngineProfile) (models.EngineProfile, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// EngineProfileService backs CRUD for the engine_profiles table.
type EngineProfileService struct {
	queries  *sqlc.Queries
	registry *engines.Registry
	logger   *slog.Logger
}

// NewEngineProfileService constructs an EngineProfileService. registry
// is used to validate that `engine` references a known plugin.
func NewEngineProfileService(q *sqlc.Queries, reg *engines.Registry, logger *slog.Logger) *EngineProfileService {
	return &EngineProfileService{queries: q, registry: reg, logger: logger}
}

// List returns profiles, optionally filtered to a single engine name.
func (s *EngineProfileService) List(ctx context.Context, engine string) ([]models.EngineProfile, error) {
	var rows []sqlc.EngineProfile
	var err error
	if engine == "" {
		rows, err = s.queries.ListEngineProfiles(ctx)
	} else {
		rows, err = s.queries.ListEngineProfilesByEngine(ctx, engine)
	}
	if err != nil {
		return nil, err
	}
	out := make([]models.EngineProfile, 0, len(rows))
	for i := range rows {
		out = append(out, engineProfileFromRow(rows[i]))
	}
	return out, nil
}

// Get returns a single profile by id, or ErrNotFound.
func (s *EngineProfileService) Get(ctx context.Context, id uuid.UUID) (models.EngineProfile, error) {
	row, err := s.queries.GetEngineProfile(ctx, toPgUUID(id))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.EngineProfile{}, ErrNotFound
		}
		return models.EngineProfile{}, err
	}
	return engineProfileFromRow(row), nil
}

// Create inserts a new profile after validating that the engine name
// is registered.
func (s *EngineProfileService) Create(ctx context.Context, p *models.EngineProfile) (models.EngineProfile, error) {
	if err := s.validate(p); err != nil {
		return models.EngineProfile{}, err
	}
	buildJSON, err := marshalConfig(p.BuildConfig)
	if err != nil {
		return models.EngineProfile{}, err
	}
	runtimeJSON, err := marshalConfig(p.RuntimeConfig)
	if err != nil {
		return models.EngineProfile{}, err
	}
	row, err := s.queries.CreateEngineProfile(ctx, sqlc.CreateEngineProfileParams{
		Name:          p.Name,
		Engine:        p.Engine,
		Description:   p.Description,
		BuildConfig:   buildJSON,
		RuntimeConfig: runtimeJSON,
		IsDefault:     p.IsDefault,
	})
	if err != nil {
		return models.EngineProfile{}, err
	}
	s.logger.Info("engine profile created", "id", fromPgUUID(row.ID), "engine", p.Engine, "name", p.Name)
	return engineProfileFromRow(row), nil
}

// Update modifies an existing profile. Engine name is not editable —
// change the name/description/configs instead.
func (s *EngineProfileService) Update(ctx context.Context, p *models.EngineProfile) (models.EngineProfile, error) {
	if p.ID == uuid.Nil {
		return models.EngineProfile{}, fmt.Errorf("engine profile: id required")
	}
	buildJSON, err := marshalConfig(p.BuildConfig)
	if err != nil {
		return models.EngineProfile{}, err
	}
	runtimeJSON, err := marshalConfig(p.RuntimeConfig)
	if err != nil {
		return models.EngineProfile{}, err
	}
	row, err := s.queries.UpdateEngineProfile(ctx, sqlc.UpdateEngineProfileParams{
		ID:            toPgUUID(p.ID),
		Name:          p.Name,
		Description:   p.Description,
		BuildConfig:   buildJSON,
		RuntimeConfig: runtimeJSON,
		IsDefault:     p.IsDefault,
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.EngineProfile{}, ErrNotFound
		}
		return models.EngineProfile{}, err
	}
	return engineProfileFromRow(row), nil
}

// Delete removes a profile by id.
func (s *EngineProfileService) Delete(ctx context.Context, id uuid.UUID) error {
	return s.queries.DeleteEngineProfile(ctx, toPgUUID(id))
}

func (s *EngineProfileService) validate(p *models.EngineProfile) error {
	if p.Name == "" {
		return fmt.Errorf("engine profile: name required")
	}
	if p.Engine == "" {
		return fmt.Errorf("engine profile: engine required")
	}
	if s.registry != nil {
		if _, ok := s.registry.Get(p.Engine); !ok {
			return fmt.Errorf("engine profile: unknown engine %q", p.Engine)
		}
	}
	return nil
}

func engineProfileFromRow(row sqlc.EngineProfile) models.EngineProfile { //nolint:gocritic // value receiver for clean conversion API
	return models.EngineProfile{
		ID:            fromPgUUID(row.ID),
		Name:          row.Name,
		Engine:        row.Engine,
		Description:   row.Description,
		BuildConfig:   unmarshalConfig(row.BuildConfig),
		RuntimeConfig: unmarshalConfig(row.RuntimeConfig),
		IsDefault:     row.IsDefault,
		CreatedAt:     timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:     timeFromPgTimestamptz(row.UpdatedAt),
	}
}

// marshalConfig encodes a map to JSON, substituting an empty object
// when the map is nil.
func marshalConfig(m map[string]any) ([]byte, error) {
	if m == nil {
		return []byte("{}"), nil
	}
	return json.Marshal(m)
}

// unmarshalConfig decodes a JSONB column into a map. Invalid JSON is
// returned as a nil map rather than an error — the database holds the
// source of truth, so the caller can detect corruption via the
// surrounding logs.
func unmarshalConfig(raw []byte) map[string]any {
	if len(raw) == 0 {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		return nil
	}
	if out == nil {
		out = map[string]any{}
	}
	return out
}
