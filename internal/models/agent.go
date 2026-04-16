// Package models holds domain structs used by the API and service
// layers. These are deliberately independent from sqlc-generated
// types so handlers don't leak pgtype into JSON.
package models

import (
	"time"

	"github.com/google/uuid"
)

// AgentStatus is a BONNIE agent's liveness state as observed by the
// registry health loop.
type AgentStatus string

// Known agent statuses.
const (
	AgentStatusOnline  AgentStatus = "online"
	AgentStatusOffline AgentStatus = "offline"
)

// Agent is the API representation of a BONNIE agent row.
type Agent struct {
	ID         uuid.UUID   `json:"id"`
	Name       string      `json:"name"`
	URL        string      `json:"url"`
	Token      string      `json:"-"` // never serialized — operators fetch from the DB.
	Status     AgentStatus `json:"status"`
	LastSeenAt *time.Time  `json:"last_seen_at,omitempty"`
	CreatedAt  time.Time   `json:"created_at"`
	UpdatedAt  time.Time   `json:"updated_at"`
}
