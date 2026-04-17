package campaign

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/robfig/cron/v3"

	"github.com/flag-ai/kitt/internal/models"
)

// Fetcher returns the full set of campaigns with schedules so the
// scheduler can reconcile its cron entries from the database. The
// service layer implements this.
type Fetcher interface {
	ListScheduled(ctx context.Context) ([]models.Campaign, error)
	Get(ctx context.Context, id uuid.UUID) (models.Campaign, error)
}

// Scheduler runs enabled campaigns on their cron schedules. It is a
// thin wrapper around robfig/cron/v3 that knows how to rebuild its
// entries from the canonical database state — callers invoke Reload
// after any create/update/delete to keep the cron table in sync.
type Scheduler struct {
	fetcher Fetcher
	runner  *Runner
	logger  *slog.Logger

	mu      sync.Mutex
	cron    *cron.Cron
	entries map[uuid.UUID]cron.EntryID
}

// NewScheduler constructs a Scheduler.
func NewScheduler(fetcher Fetcher, runner *Runner, logger *slog.Logger) *Scheduler {
	return &Scheduler{
		fetcher: fetcher,
		runner:  runner,
		logger:  logger,
		// Use the standard 5-field parser so "0 * * * *" works as
		// expected. The WithSeconds option is intentionally omitted —
		// seconds granularity isn't needed for benchmark campaigns.
		cron:    cron.New(cron.WithLogger(cronLogger{logger: logger})),
		entries: map[uuid.UUID]cron.EntryID{},
	}
}

// Start begins the cron ticker and does a first Reload.
func (s *Scheduler) Start(ctx context.Context) error {
	s.cron.Start()
	if err := s.Reload(ctx); err != nil {
		return err
	}
	return nil
}

// Stop shuts the cron ticker down. Safe to call multiple times.
func (s *Scheduler) Stop() {
	ctx := s.cron.Stop()
	<-ctx.Done()
}

// Reload rebuilds the in-memory cron entries from the fetcher's output.
// Campaigns with empty cron_expr or Enabled=false are skipped.
func (s *Scheduler) Reload(ctx context.Context) error {
	campaigns, err := s.fetcher.ListScheduled(ctx)
	if err != nil {
		return err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	// Remove every current entry — a full rebuild is simpler than a
	// diff and cheap enough at the scale of a single KITT server.
	for _, id := range s.entries {
		s.cron.Remove(id)
	}
	s.entries = map[uuid.UUID]cron.EntryID{}

	for i := range campaigns {
		c := campaigns[i]
		if !c.Enabled || c.CronExpr == "" {
			continue
		}
		id := c.ID // capture for the closure
		entryID, err := s.cron.AddFunc(c.CronExpr, func() {
			s.fire(context.Background(), id)
		})
		if err != nil {
			s.logger.Warn("campaign: invalid cron_expr", "campaign", c.Name, "expr", c.CronExpr, "error", err)
			continue
		}
		s.entries[c.ID] = entryID
	}
	s.logger.Debug("campaign scheduler reloaded", "count", len(s.entries))
	return nil
}

// scheduledRunTimeout caps how long a scheduled campaign run may
// execute before being cancelled. Matches the RunNow handler timeout.
const scheduledRunTimeout = 6 * time.Hour

// fire resolves the campaign by id and dispatches it through the runner.
func (s *Scheduler) fire(_ context.Context, id uuid.UUID) {
	ctx, cancel := context.WithTimeout(context.Background(), scheduledRunTimeout)
	defer cancel()
	c, err := s.fetcher.Get(ctx, id)
	if err != nil {
		s.logger.Error("campaign: scheduled fetch failed", "id", id, "error", err)
		return
	}
	if err := s.runner.Run(ctx, &c); err != nil {
		s.logger.Error("campaign: scheduled run failed", "id", id, "name", c.Name, "error", err)
	}
}

// cronLogger adapts slog.Logger to cron.Logger so we don't swallow
// library log lines.
type cronLogger struct{ logger *slog.Logger }

// Info logs a non-error cron event at debug level.
func (l cronLogger) Info(msg string, keysAndValues ...any) {
	l.logger.Debug("cron: "+msg, keysAndValues...)
}

// Error logs an error cron event at warn level.
func (l cronLogger) Error(err error, msg string, keysAndValues ...any) {
	args := append([]any{"error", err}, keysAndValues...)
	l.logger.Warn("cron: "+msg, args...)
}
