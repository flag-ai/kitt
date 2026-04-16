// Package storage provides CRUD over KITT's results tables (runs,
// benchmarks, metrics). This is the KITT 2.0 replacement for the 1.x
// ResultStore abstraction — Postgres-only, no SQLite fallback.
package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"

	"github.com/flag-ai/kitt/internal/db/sqlc"
	"github.com/flag-ai/kitt/internal/models"
)

// ErrNotFound is returned when a requested row does not exist.
var ErrNotFound = errors.New("storage: not found")

// Store is the top-level entry point for the results storage layer.
// Handlers depend on the struct directly rather than an interface
// because the surface is small and implementation variations are not
// expected in 2.x.
type Store struct {
	queries *sqlc.Queries
}

// New constructs a Store backed by sqlc-generated queries.
func New(q *sqlc.Queries) *Store {
	return &Store{queries: q}
}

// ListParams controls pagination.
type ListParams struct {
	Limit  int
	Offset int
}

// ListRuns returns runs newest-first with pagination.
func (s *Store) ListRuns(ctx context.Context, p ListParams) ([]models.Run, error) {
	// Clamp limit to [1, 500]; the SQL type is int32, and the clamp
	// guarantees the int->int32 conversion below cannot overflow.
	if p.Limit <= 0 || p.Limit > 500 {
		p.Limit = 50
	}
	// Negative offsets make no sense; very large offsets (above
	// int32's range) are also nonsensical and capped here.
	if p.Offset < 0 {
		p.Offset = 0
	}
	if p.Offset > 1_000_000 {
		p.Offset = 1_000_000
	}
	rows, err := s.queries.ListRuns(ctx, sqlc.ListRunsParams{
		Limit:  int32(p.Limit),  // #nosec G115 -- bounded 1..500 above
		Offset: int32(p.Offset), // #nosec G115 -- bounded 0..1_000_000 above
	})
	if err != nil {
		return nil, err
	}
	out := make([]models.Run, 0, len(rows))
	for i := range rows {
		out = append(out, runFromRow(rows[i]))
	}
	return out, nil
}

// GetRun returns a single run with its benchmarks and metrics.
func (s *Store) GetRun(ctx context.Context, id uuid.UUID) (models.RunDetail, error) {
	row, err := s.queries.GetRun(ctx, toPgUUID(id))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.RunDetail{}, ErrNotFound
		}
		return models.RunDetail{}, err
	}
	run := runFromRow(row)

	bRows, err := s.queries.ListBenchmarksForRun(ctx, row.ID)
	if err != nil {
		return models.RunDetail{}, err
	}
	benchmarks := make([]models.BenchmarkResult, 0, len(bRows))
	for i := range bRows {
		benchmarks = append(benchmarks, benchmarkResultFromRow(bRows[i]))
	}

	mRows, err := s.queries.ListMetricsForRun(ctx, row.ID)
	if err != nil {
		return models.RunDetail{}, err
	}
	metrics := make([]models.Metric, 0, len(mRows))
	for i := range mRows {
		metrics = append(metrics, metricFromRow(mRows[i]))
	}

	return models.RunDetail{Run: run, Benchmarks: benchmarks, Metrics: metrics}, nil
}

// CreateRun inserts a pending run. The caller later updates status
// via SetRunStatus as the run progresses.
func (s *Store) CreateRun(ctx context.Context, r *models.Run) (models.Run, error) {
	if r.Model == "" || r.Engine == "" {
		return models.Run{}, fmt.Errorf("storage: model and engine are required")
	}
	params := sqlc.CreateRunParams{
		Model:  r.Model,
		Engine: r.Engine,
		Status: string(r.Status),
	}
	if r.Status == "" {
		params.Status = string(models.RunStatusPending)
	}
	if r.CampaignID != nil {
		params.CampaignID = toPgUUID(*r.CampaignID)
	}
	if r.AgentID != nil {
		params.AgentID = toPgUUID(*r.AgentID)
	}
	if r.HardwareID != nil {
		params.HardwareID = toPgUUID(*r.HardwareID)
	}
	if r.EngineProfileID != nil {
		params.EngineProfileID = toPgUUID(*r.EngineProfileID)
	}
	row, err := s.queries.CreateRun(ctx, params)
	if err != nil {
		return models.Run{}, err
	}
	return runFromRow(row), nil
}

// runFromRow converts the sqlc row to the API model.
func runFromRow(row sqlc.Run) models.Run { //nolint:gocritic // value receiver for clean conversion API
	r := models.Run{
		ID:         fromPgUUID(row.ID),
		Model:      row.Model,
		Engine:     row.Engine,
		Status:     models.RunStatus(row.Status),
		Error:      row.Error,
		StartedAt:  timePtrFromPgTimestamptz(row.StartedAt),
		FinishedAt: timePtrFromPgTimestamptz(row.FinishedAt),
		CreatedAt:  row.CreatedAt.Time,
		UpdatedAt:  row.UpdatedAt.Time,
	}
	if row.CampaignID.Valid {
		id := fromPgUUID(row.CampaignID)
		r.CampaignID = &id
	}
	if row.AgentID.Valid {
		id := fromPgUUID(row.AgentID)
		r.AgentID = &id
	}
	if row.HardwareID.Valid {
		id := fromPgUUID(row.HardwareID)
		r.HardwareID = &id
	}
	if row.EngineProfileID.Valid {
		id := fromPgUUID(row.EngineProfileID)
		r.EngineProfileID = &id
	}
	return r
}

func benchmarkResultFromRow(row sqlc.Benchmark) models.BenchmarkResult { //nolint:gocritic // value receiver for clean conversion API
	b := models.BenchmarkResult{
		ID:         fromPgUUID(row.ID),
		RunID:      fromPgUUID(row.RunID),
		Benchmark:  row.Benchmark,
		Status:     row.Status,
		StartedAt:  timePtrFromPgTimestamptz(row.StartedAt),
		FinishedAt: timePtrFromPgTimestamptz(row.FinishedAt),
		CreatedAt:  row.CreatedAt.Time,
	}
	if row.Score.Valid {
		v := row.Score.Float64
		b.Score = &v
	}
	if row.DurationMs.Valid {
		v := row.DurationMs.Int64
		b.DurationMS = &v
	}
	if len(row.RawJson) > 0 {
		var raw map[string]any
		if err := json.Unmarshal(row.RawJson, &raw); err == nil {
			b.RawJSON = raw
		}
	}
	return b
}

func metricFromRow(row sqlc.Metric) models.Metric { //nolint:gocritic // value receiver for clean conversion API
	m := models.Metric{
		ID:         row.ID,
		RunID:      fromPgUUID(row.RunID),
		Name:       row.Name,
		Value:      row.Value,
		Unit:       row.Unit,
		RecordedAt: row.RecordedAt.Time,
	}
	if row.BenchmarkID.Valid {
		id := fromPgUUID(row.BenchmarkID)
		m.BenchmarkID = &id
	}
	return m
}

// toPgUUID / fromPgUUID / timePtrFromPgTimestamptz are intentionally
// duplicated here (rather than imported from service) so storage
// doesn't depend on the service package.

func toPgUUID(id uuid.UUID) pgtype.UUID {
	return pgtype.UUID{Bytes: [16]byte(id), Valid: true}
}

func fromPgUUID(id pgtype.UUID) uuid.UUID {
	return uuid.UUID(id.Bytes)
}

func timePtrFromPgTimestamptz(ts pgtype.Timestamptz) *time.Time {
	if ts.Valid {
		return &ts.Time
	}
	return nil
}
