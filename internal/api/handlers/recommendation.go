package handlers

import (
	"log/slog"
	"net/http"
	"strconv"

	"github.com/flag-ai/kitt/internal/engines"
	"github.com/flag-ai/kitt/internal/recommendation"
)

// RecommendationHandler serves /api/v1/recommend.
type RecommendationHandler struct {
	recommender *recommendation.Recommender
	logger      *slog.Logger
}

// NewRecommendationHandler constructs a RecommendationHandler.
func NewRecommendationHandler(r *recommendation.Recommender, logger *slog.Logger) *RecommendationHandler {
	return &RecommendationHandler{recommender: r, logger: logger}
}

// Recommend handles GET /api/v1/recommend with query parameters:
//
//	vram=<int>           GPU VRAM in GiB
//	task=<quality|performance|coding|multimodal>
//	unified=<bool>       true when host is unified memory (Apple / Spark)
//	format=<fmt>         repeated; at least one match required
//
// POST is also accepted with a JSON body of the same shape for clients
// that prefer structured requests.
func (h *RecommendationHandler) Recommend(w http.ResponseWriter, r *http.Request) {
	var req recommendation.Request
	if r.Method == http.MethodPost {
		if err := decodeBody(w, r, &req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid json body")
			return
		}
	} else {
		q := r.URL.Query()
		if v := q.Get("vram"); v != "" {
			if n, err := strconv.Atoi(v); err == nil {
				req.GPUVRAMGiB = n
			}
		}
		req.Task = q.Get("task")
		if q.Get("unified") == "true" {
			req.UnifiedMemory = true
		}
		for _, f := range q["format"] {
			req.DesiredFormats = append(req.DesiredFormats, engines.Format(f))
		}
	}
	writeJSON(w, http.StatusOK, h.recommender.Recommend(&req))
}
