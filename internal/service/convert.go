// Package service contains business-logic services for the KITT API.
package service

import (
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgtype"
)

// toPgUUID converts a google/uuid.UUID to a pgtype.UUID.
func toPgUUID(id uuid.UUID) pgtype.UUID {
	return pgtype.UUID{Bytes: [16]byte(id), Valid: true}
}

// fromPgUUID converts a pgtype.UUID to a google/uuid.UUID.
func fromPgUUID(id pgtype.UUID) uuid.UUID {
	return uuid.UUID(id.Bytes)
}

// timeFromPgTimestamptz converts a pgtype.Timestamptz to time.Time.
// Returns the zero time when the pg value is NULL.
func timeFromPgTimestamptz(ts pgtype.Timestamptz) time.Time {
	if ts.Valid {
		return ts.Time
	}
	return time.Time{}
}

// timePtrFromPgTimestamptz converts a pgtype.Timestamptz to *time.Time.
// Returns nil when the pg value is NULL.
func timePtrFromPgTimestamptz(ts pgtype.Timestamptz) *time.Time {
	if ts.Valid {
		return &ts.Time
	}
	return nil
}

// pgTimestamptz builds a valid pgtype.Timestamptz from a time.Time.
func pgTimestamptz(t time.Time) pgtype.Timestamptz {
	return pgtype.Timestamptz{Time: t, Valid: true}
}

// parseUUIDString parses a UUID string. Used by adapters that receive
// agent ids as strings from flag-commons.
func parseUUIDString(s string) (uuid.UUID, error) {
	id, err := uuid.Parse(s)
	if err != nil {
		return uuid.Nil, fmt.Errorf("parse uuid %q: %w", s, err)
	}
	return id, nil
}
