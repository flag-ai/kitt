package service

import (
	"context"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/flag-ai/kitt/internal/benchmarks"
	"github.com/flag-ai/kitt/internal/db/sqlc"
	"github.com/flag-ai/kitt/internal/models"
)

// BenchmarkRegistryServicer is the handler-facing interface.
type BenchmarkRegistryServicer interface {
	List(ctx context.Context, kind benchmarks.Kind) ([]models.BenchmarkRegistryEntry, error)
	Get(ctx context.Context, id uuid.UUID) (models.BenchmarkRegistryEntry, error)
	Create(ctx context.Context, entry *models.BenchmarkRegistryEntry) (models.BenchmarkRegistryEntry, error)
	Update(ctx context.Context, entry *models.BenchmarkRegistryEntry) (models.BenchmarkRegistryEntry, error)
	Delete(ctx context.Context, id uuid.UUID) error
}

// BenchmarkRegistryService backs the /api/v1/benchmarks CRUD routes.
type BenchmarkRegistryService struct {
	queries *sqlc.Queries
	logger  *slog.Logger
}

// NewBenchmarkRegistryService constructs the service.
func NewBenchmarkRegistryService(q *sqlc.Queries, logger *slog.Logger) *BenchmarkRegistryService {
	return &BenchmarkRegistryService{queries: q, logger: logger}
}

// List returns every benchmark, optionally filtered by kind.
func (s *BenchmarkRegistryService) List(ctx context.Context, kind benchmarks.Kind) ([]models.BenchmarkRegistryEntry, error) {
	var rows []sqlc.BenchmarkRegistry
	var err error
	if kind == "" {
		rows, err = s.queries.ListBenchmarkRegistry(ctx)
	} else {
		rows, err = s.queries.ListBenchmarkRegistryByKind(ctx, string(kind))
	}
	if err != nil {
		return nil, err
	}
	out := make([]models.BenchmarkRegistryEntry, 0, len(rows))
	for i := range rows {
		out = append(out, benchmarkFromRow(rows[i]))
	}
	return out, nil
}

// Get returns a single entry by id, or ErrNotFound.
func (s *BenchmarkRegistryService) Get(ctx context.Context, id uuid.UUID) (models.BenchmarkRegistryEntry, error) {
	row, err := s.queries.GetBenchmarkRegistry(ctx, toPgUUID(id))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.BenchmarkRegistryEntry{}, ErrNotFound
		}
		return models.BenchmarkRegistryEntry{}, err
	}
	return benchmarkFromRow(row), nil
}

// Create validates and inserts a new benchmark.
func (s *BenchmarkRegistryService) Create(ctx context.Context, entry *models.BenchmarkRegistryEntry) (models.BenchmarkRegistryEntry, error) {
	if err := validateBenchmark(entry); err != nil {
		return models.BenchmarkRegistryEntry{}, err
	}
	cfgJSON, err := marshalConfig(entry.Config)
	if err != nil {
		return models.BenchmarkRegistryEntry{}, err
	}
	row, err := s.queries.CreateBenchmarkRegistry(ctx, sqlc.CreateBenchmarkRegistryParams{
		Name:        entry.Name,
		Kind:        string(entry.Kind),
		Category:    string(entry.Category),
		Description: entry.Description,
		Source:      entry.Source,
		Config:      cfgJSON,
		Enabled:     entry.Enabled,
	})
	if err != nil {
		return models.BenchmarkRegistryEntry{}, err
	}
	s.logger.Info("benchmark registered", "name", entry.Name, "kind", entry.Kind)
	return benchmarkFromRow(row), nil
}

// Update modifies an existing benchmark. Name is immutable — callers
// should delete and re-create if they need to rename.
func (s *BenchmarkRegistryService) Update(ctx context.Context, entry *models.BenchmarkRegistryEntry) (models.BenchmarkRegistryEntry, error) {
	if entry.ID == uuid.Nil {
		return models.BenchmarkRegistryEntry{}, fmt.Errorf("benchmark: id required")
	}
	if err := validateBenchmark(entry); err != nil {
		return models.BenchmarkRegistryEntry{}, err
	}
	cfgJSON, err := marshalConfig(entry.Config)
	if err != nil {
		return models.BenchmarkRegistryEntry{}, err
	}
	row, err := s.queries.UpdateBenchmarkRegistry(ctx, sqlc.UpdateBenchmarkRegistryParams{
		ID:          toPgUUID(entry.ID),
		Kind:        string(entry.Kind),
		Category:    string(entry.Category),
		Description: entry.Description,
		Source:      entry.Source,
		Config:      cfgJSON,
		Enabled:     entry.Enabled,
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.BenchmarkRegistryEntry{}, ErrNotFound
		}
		return models.BenchmarkRegistryEntry{}, err
	}
	return benchmarkFromRow(row), nil
}

// Delete removes a benchmark by id.
func (s *BenchmarkRegistryService) Delete(ctx context.Context, id uuid.UUID) error {
	return s.queries.DeleteBenchmarkRegistry(ctx, toPgUUID(id))
}

// validateBenchmark enforces required fields and kind whitelist.
func validateBenchmark(e *models.BenchmarkRegistryEntry) error {
	if e.Name == "" {
		return fmt.Errorf("benchmark: name required")
	}
	switch e.Kind {
	case benchmarks.KindYAML, benchmarks.KindContainer:
		// ok
	default:
		return fmt.Errorf("benchmark: unknown kind %q (want yaml or container)", e.Kind)
	}
	if e.Category == "" {
		return fmt.Errorf("benchmark: category required")
	}
	return nil
}

// benchmarkFromRow converts a sqlc.BenchmarkRegistry row to the API model.
func benchmarkFromRow(row sqlc.BenchmarkRegistry) models.BenchmarkRegistryEntry { //nolint:gocritic // value receiver for clean conversion API
	return models.BenchmarkRegistryEntry{
		ID:          fromPgUUID(row.ID),
		Name:        row.Name,
		Kind:        benchmarks.Kind(row.Kind),
		Category:    benchmarks.Category(row.Category),
		Description: row.Description,
		Source:      row.Source,
		Config:      unmarshalConfig(row.Config),
		Enabled:     row.Enabled,
		CreatedAt:   timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:   timeFromPgTimestamptz(row.UpdatedAt),
	}
}
