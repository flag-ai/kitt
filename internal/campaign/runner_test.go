package campaign

import (
	"context"
	"io"
	"log/slog"
	"testing"

	"github.com/google/uuid"

	"github.com/flag-ai/kitt/internal/models"
)

func quietLogger() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func TestRunner_RunRejectsEmptyConfig(t *testing.T) {
	r := NewRunner(nil, NewState(), nil, quietLogger())
	c := &models.Campaign{
		ID: uuid.New(),
		Config: models.CampaignConfig{
			Models:     []string{"m"},
			Engines:    []string{},
			Benchmarks: []string{"b"},
		},
	}
	if err := r.Run(context.Background(), c); err == nil {
		t.Fatal("expected error for empty engines")
	}
}

func TestRunner_RunNoAgentsFails(t *testing.T) {
	r := NewRunner(nil, NewState(), nil, quietLogger())
	c := &models.Campaign{
		ID:   uuid.New(),
		Name: "t",
		Config: models.CampaignConfig{
			Models:     []string{"m"},
			Engines:    []string{"vllm"},
			Benchmarks: []string{"mmlu"},
		},
	}
	if err := r.Run(context.Background(), c); err == nil {
		t.Fatal("expected error when no agents available")
	}
}

func TestValidateConfig(t *testing.T) {
	good := &models.CampaignConfig{
		Models: []string{"m"}, Engines: []string{"e"}, Benchmarks: []string{"b"},
	}
	if err := validateConfig(good); err != nil {
		t.Fatalf("good config rejected: %v", err)
	}
	bad := &models.CampaignConfig{Engines: []string{"e"}, Benchmarks: []string{"b"}}
	if err := validateConfig(bad); err == nil {
		t.Fatal("expected error for missing models")
	}
}
