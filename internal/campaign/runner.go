package campaign

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/bonnie"
	"github.com/flag-ai/kitt/internal/models"
)

// Runner executes campaign configs. The 2.0-scaffold implementation
// expands the config into (model × engine × benchmark × agent) tuples
// and logs each — real BONNIE dispatch lands in later PRs once the
// paired-run endpoint is wired up. The Runner publishes state
// transitions to the shared State so the SSE status endpoint can
// surface progress in real time.
type Runner struct {
	registry *bonnie.Registry
	state    *State
	logger   *slog.Logger
}

// NewRunner constructs a Runner.
func NewRunner(registry *bonnie.Registry, state *State, logger *slog.Logger) *Runner {
	return &Runner{registry: registry, state: state, logger: logger}
}

// Run expands cfg and executes every tuple against the selected
// agents. Publishes incremental status via Runner.state. Returns an
// error only when the campaign is unrunnable before any dispatch —
// in-flight per-run failures are recorded on the status and in PR F
// on the runs table.
func (r *Runner) Run(ctx context.Context, campaign *models.Campaign) error {
	if err := validateConfig(&campaign.Config); err != nil {
		r.publish(campaign.ID, "failed", err.Error(), time.Time{})
		return err
	}

	started := time.Now().UTC()
	r.publish(campaign.ID, "running",
		fmt.Sprintf("expanding %d models × %d engines × %d benchmarks",
			len(campaign.Config.Models), len(campaign.Config.Engines), len(campaign.Config.Benchmarks)),
		started)

	agents := r.selectAgents(campaign.Config.AgentNames)
	if len(agents) == 0 {
		err := fmt.Errorf("campaign: no agents available for %q", campaign.Name)
		r.publish(campaign.ID, "failed", err.Error(), started)
		return err
	}

	// Enumerate every tuple — actual dispatch is stubbed in the scaffold
	// and replaced with bonnie.Client.RunBenchmark in PR F+.
	total := 0
	for _, model := range campaign.Config.Models {
		for _, engine := range campaign.Config.Engines {
			for _, benchmark := range campaign.Config.Benchmarks {
				total++
				r.logger.Debug("campaign tuple enqueued",
					"campaign", campaign.Name,
					"model", model, "engine", engine, "benchmark", benchmark,
					"agents", len(agents))
				// Yield so the status stream can observe the updated
				// progress counter as the runner walks the matrix.
				select {
				case <-ctx.Done():
					r.publish(campaign.ID, "cancelled", ctx.Err().Error(), started)
					return ctx.Err()
				default:
				}
			}
		}
	}

	r.publish(campaign.ID, "succeeded",
		fmt.Sprintf("enqueued %d runs across %d agents", total, len(agents)),
		started)
	return nil
}

func (r *Runner) publish(id uuid.UUID, state, msg string, started time.Time) {
	r.state.Set(&models.CampaignRunStatus{
		CampaignID: id,
		State:      state,
		Message:    msg,
		StartedAt:  started,
		UpdatedAt:  time.Now().UTC(),
	})
}

// selectAgents narrows the registry to the configured agent names. An
// empty names slice means every registered agent.
func (r *Runner) selectAgents(names []string) []bonnie.Agent {
	if r.registry == nil {
		return nil
	}
	all := r.registry.Agents()
	if len(names) == 0 {
		return all
	}
	want := make(map[string]struct{}, len(names))
	for _, n := range names {
		want[n] = struct{}{}
	}
	out := make([]bonnie.Agent, 0, len(names))
	for i := range all {
		if _, ok := want[all[i].Name]; ok {
			out = append(out, all[i])
		}
	}
	return out
}

// validateConfig enforces non-empty model/engine/benchmark sets.
func validateConfig(cfg *models.CampaignConfig) error {
	if len(cfg.Models) == 0 {
		return fmt.Errorf("campaign: at least one model is required")
	}
	if len(cfg.Engines) == 0 {
		return fmt.Errorf("campaign: at least one engine is required")
	}
	if len(cfg.Benchmarks) == 0 {
		return fmt.Errorf("campaign: at least one benchmark is required")
	}
	return nil
}
