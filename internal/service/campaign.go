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
	"github.com/flag-ai/kitt/internal/models"
)

// CampaignServicer is the handler-facing interface.
type CampaignServicer interface {
	List(ctx context.Context) ([]models.Campaign, error)
	Get(ctx context.Context, id uuid.UUID) (models.Campaign, error)
	Create(ctx context.Context, c *models.Campaign) (models.Campaign, error)
	UpdateSchedule(ctx context.Context, id uuid.UUID, cronExpr string, enabled bool) (models.Campaign, error)
	Delete(ctx context.Context, id uuid.UUID) error

	// ListScheduled returns campaigns with a non-empty cron_expr.
	// Implements campaign.CampaignFetcher so the scheduler can reload.
	ListScheduled(ctx context.Context) ([]models.Campaign, error)
}

// SchedulerReloader notifies the in-app scheduler that campaign rows
// have changed and it should rebuild its cron table.
type SchedulerReloader interface {
	Reload(ctx context.Context) error
}

// CampaignService persists campaign rows and keeps the scheduler
// synchronized.
type CampaignService struct {
	queries   *sqlc.Queries
	scheduler SchedulerReloader
	logger    *slog.Logger
}

// NewCampaignService constructs a CampaignService. scheduler may be
// nil when constructed — use SetScheduler later to avoid the
// service/scheduler initialization cycle in main.
func NewCampaignService(q *sqlc.Queries, scheduler SchedulerReloader, logger *slog.Logger) *CampaignService {
	return &CampaignService{queries: q, scheduler: scheduler, logger: logger}
}

// SetScheduler wires the scheduler after construction. Called once
// during bootstrap to close the cycle between the service (which
// needs the scheduler for Reload) and the scheduler (which needs the
// service as a CampaignFetcher).
func (s *CampaignService) SetScheduler(scheduler SchedulerReloader) {
	s.scheduler = scheduler
}

// List returns every campaign.
func (s *CampaignService) List(ctx context.Context) ([]models.Campaign, error) {
	rows, err := s.queries.ListCampaigns(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]models.Campaign, 0, len(rows))
	for i := range rows {
		c, cerr := campaignFromRow(rows[i])
		if cerr != nil {
			s.logger.Warn("campaign: corrupted row skipped", "id", fromPgUUID(rows[i].ID), "error", cerr)
			continue
		}
		out = append(out, c)
	}
	return out, nil
}

// ListScheduled returns every enabled campaign with a non-empty
// cron_expr. The scheduler calls this during reload.
func (s *CampaignService) ListScheduled(ctx context.Context) ([]models.Campaign, error) {
	all, err := s.List(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]models.Campaign, 0, len(all))
	for i := range all {
		if all[i].Enabled && all[i].CronExpr != "" {
			out = append(out, all[i])
		}
	}
	return out, nil
}

// Get returns a single campaign by id, or ErrNotFound.
func (s *CampaignService) Get(ctx context.Context, id uuid.UUID) (models.Campaign, error) {
	row, err := s.queries.GetCampaign(ctx, toPgUUID(id))
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.Campaign{}, ErrNotFound
		}
		return models.Campaign{}, err
	}
	return campaignFromRow(row)
}

// Create validates and inserts a campaign, then reloads the scheduler.
func (s *CampaignService) Create(ctx context.Context, c *models.Campaign) (models.Campaign, error) {
	if c.Name == "" {
		return models.Campaign{}, fmt.Errorf("campaign: name required")
	}
	cfgJSON, err := json.Marshal(c.Config)
	if err != nil {
		return models.Campaign{}, fmt.Errorf("campaign: marshal config: %w", err)
	}
	row, err := s.queries.CreateCampaign(ctx, sqlc.CreateCampaignParams{
		Name:        c.Name,
		Description: c.Description,
		Config:      cfgJSON,
		CronExpr:    c.CronExpr,
		Enabled:     c.Enabled,
	})
	if err != nil {
		return models.Campaign{}, err
	}
	s.reloadScheduler(ctx)
	return campaignFromRow(row)
}

// UpdateSchedule updates only cron_expr and enabled, then reloads.
// Use this instead of a generic PUT so schedule changes don't require
// the full config payload round-trip.
func (s *CampaignService) UpdateSchedule(ctx context.Context, id uuid.UUID, cronExpr string, enabled bool) (models.Campaign, error) {
	row, err := s.queries.UpdateCampaignSchedule(ctx, sqlc.UpdateCampaignScheduleParams{
		ID:       toPgUUID(id),
		CronExpr: cronExpr,
		Enabled:  enabled,
	})
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return models.Campaign{}, ErrNotFound
		}
		return models.Campaign{}, err
	}
	s.reloadScheduler(ctx)
	return campaignFromRow(row)
}

// Delete removes a campaign by id and reloads the scheduler.
func (s *CampaignService) Delete(ctx context.Context, id uuid.UUID) error {
	if err := s.queries.DeleteCampaign(ctx, toPgUUID(id)); err != nil {
		return err
	}
	s.reloadScheduler(ctx)
	return nil
}

func (s *CampaignService) reloadScheduler(ctx context.Context) {
	if s.scheduler == nil {
		return
	}
	if err := s.scheduler.Reload(ctx); err != nil {
		s.logger.Warn("campaign: scheduler reload failed", "error", err)
	}
}

// campaignFromRow converts a sqlc.Campaign row to the API model.
func campaignFromRow(row sqlc.Campaign) (models.Campaign, error) { //nolint:gocritic // value receiver for clean conversion API
	var cfg models.CampaignConfig
	if len(row.Config) > 0 {
		if err := json.Unmarshal(row.Config, &cfg); err != nil {
			return models.Campaign{}, fmt.Errorf("campaign: unmarshal config: %w", err)
		}
	}
	return models.Campaign{
		ID:          fromPgUUID(row.ID),
		Name:        row.Name,
		Description: row.Description,
		Config:      cfg,
		CronExpr:    row.CronExpr,
		Enabled:     row.Enabled,
		CreatedAt:   timeFromPgTimestamptz(row.CreatedAt),
		UpdatedAt:   timeFromPgTimestamptz(row.UpdatedAt),
	}, nil
}
