package service

import (
	"testing"

	"github.com/flag-ai/kitt/internal/benchmarks"
	"github.com/flag-ai/kitt/internal/models"
)

func TestValidateBenchmark(t *testing.T) {
	cases := []struct {
		name    string
		entry   models.BenchmarkRegistryEntry
		wantErr bool
	}{
		{
			name:    "valid yaml",
			entry:   models.BenchmarkRegistryEntry{Name: "mmlu", Kind: benchmarks.KindYAML, Category: benchmarks.CategoryQuality},
			wantErr: false,
		},
		{
			name:    "valid container",
			entry:   models.BenchmarkRegistryEntry{Name: "humaneval", Kind: benchmarks.KindContainer, Category: benchmarks.CategoryCoding},
			wantErr: false,
		},
		{
			name:    "missing name",
			entry:   models.BenchmarkRegistryEntry{Kind: benchmarks.KindYAML, Category: benchmarks.CategoryQuality},
			wantErr: true,
		},
		{
			name:    "unknown kind",
			entry:   models.BenchmarkRegistryEntry{Name: "x", Kind: "not-a-kind", Category: benchmarks.CategoryQuality},
			wantErr: true,
		},
		{
			name:    "missing category",
			entry:   models.BenchmarkRegistryEntry{Name: "x", Kind: benchmarks.KindYAML},
			wantErr: true,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateBenchmark(&tc.entry)
			if (err != nil) != tc.wantErr {
				t.Fatalf("err = %v, wantErr = %v", err, tc.wantErr)
			}
		})
	}
}
