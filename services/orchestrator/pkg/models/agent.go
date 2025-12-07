package models

import (
	"time"
	"github.com/google/uuid"
)

// Agent represents an autonomous agent in the system
type Agent struct {
	ID           string                 `json:"id"`
	Name         string                 `json:"name"`
	Type         string                 `json:"type"`
	Status       AgentStatus            `json:"status"`
	Capabilities []string               `json:"capabilities"`
	Config       map[string]interface{} `json:"config"`
	LastSeen     time.Time              `json:"last_seen"`
	CreatedAt    time.Time              `json:"created_at"`
	UpdatedAt    time.Time              `json:"updated_at"`
	Metadata     map[string]string      `json:"metadata"`
}

// AgentStatus represents the current status of an agent
type AgentStatus string

const (
	AgentStatusIdle      AgentStatus = "idle"
	AgentStatusActive    AgentStatus = "active"
	AgentStatusBusy      AgentStatus = "busy"
	AgentStatusOffline   AgentStatus = "offline"
	AgentStatusError     AgentStatus = "error"
	AgentStatusTerminated AgentStatus = "terminated"
)

// Task represents a unit of work to be executed
type Task struct {
	ID          string                 `json:"id"`
	AgentID     string                 `json:"agent_id"`
	Type        string                 `json:"type"`
	Priority    int                    `json:"priority"`
	Status      TaskStatus             `json:"status"`
	Payload     map[string]interface{} `json:"payload"`
	Result      map[string]interface{} `json:"result"`
	Error       string                 `json:"error"`
	CreatedAt   time.Time              `json:"created_at"`
	StartedAt   *time.Time             `json:"started_at,omitempty"`
	CompletedAt *time.Time             `json:"completed_at,omitempty"`
	Timeout     time.Duration          `json:"timeout"`
	WorkflowID  string                 `json:"workflow_id"`
	Step        int                    `json:"step"`
}

// TaskStatus represents the current status of a task
type TaskStatus string

const (
	TaskStatusPending   TaskStatus = "pending"
	TaskStatusRunning   TaskStatus = "running"
	TaskStatusCompleted TaskStatus = "completed"
	TaskStatusFailed    TaskStatus = "failed"
	TaskStatusCancelled TaskStatus = "cancelled"
	TaskStatusTimeout   TaskStatus = "timeout"
)

// Workflow represents a sequence of tasks
type Workflow struct {
	ID          string                 `json:"id"`
	Name        string                 `json:"name"`
	Description string                 `json:"description"`
	Tasks       []WorkflowStep         `json:"tasks"`
	Status      WorkflowStatus         `json:"status"`
	CreatedAt   time.Time              `json:"created_at"`
	UpdatedAt   time.Time              `json:"updated_at"`
	Config      map[string]interface{} `json:"config"`
}

// WorkflowStep represents a step in a workflow
type WorkflowStep struct {
	ID       string                 `json:"id"`
	Type     string                 `json:"type"`
	Agent    string                 `json:"agent"`
	Payload  map[string]interface{} `json:"payload"`
	Parallel bool                   `json:"parallel"`
	Timeout  time.Duration          `json:"timeout"`
}

// WorkflowStatus represents the current status of a workflow
type WorkflowStatus string

const (
	WorkflowStatusDraft     WorkflowStatus = "draft"
	WorkflowStatusActive    WorkflowStatus = "active"
	WorkflowStatusPaused    WorkflowStatus = "paused"
	WorkflowStatusCompleted WorkflowStatus = "completed"
	WorkflowStatusFailed    WorkflowStatus = "failed"
	WorkflowStatusCancelled WorkflowStatus = "cancelled"
)

// Schedule represents a scheduled task or workflow
type Schedule struct {
	ID          string                 `json:"id"`
	Name        string                 `json:"name"`
	Type        string                 `json:"type"` // "task" or "workflow"
	TargetID    string                 `json:"target_id"`
	Cron        string                 `json:"cron"`
	Enabled     bool                   `json:"enabled"`
	LastRun     *time.Time             `json:"last_run,omitempty"`
	NextRun     *time.Time             `json:"next_run,omitempty"`
	Payload     map[string]interface{} `json:"payload"`
	CreatedAt   time.Time              `json:"created_at"`
	UpdatedAt   time.Time              `json:"updated_at"`
}

// NewAgent creates a new agent instance
func NewAgent(name, agentType string, capabilities []string) *Agent {
	now := time.Now()
	return &Agent{
		ID:           uuid.New().String(),
		Name:         name,
		Type:         agentType,
		Status:       AgentStatusIdle,
		Capabilities: capabilities,
		Config:       make(map[string]interface{}),
		LastSeen:     now,
		CreatedAt:    now,
		UpdatedAt:    now,
		Metadata:     make(map[string]string),
	}
}

// NewTask creates a new task instance
func NewTask(agentID, taskType string, priority int, payload map[string]interface{}) *Task {
	now := time.Now()
	return &Task{
		ID:        uuid.New().String(),
		AgentID:   agentID,
		Type:      taskType,
		Priority:  priority,
		Status:    TaskStatusPending,
		Payload:   payload,
		CreatedAt: now,
		Timeout:   30 * time.Second, // Default timeout
	}
}

// NewWorkflow creates a new workflow instance
func NewWorkflow(name, description string) *Workflow {
	now := time.Now()
	return &Workflow{
		ID:          uuid.New().String(),
		Name:        name,
		Description: description,
		Tasks:       []WorkflowStep{},
		Status:      WorkflowStatusDraft,
		CreatedAt:   now,
		UpdatedAt:   now,
		Config:      make(map[string]interface{}),
	}
}

// AddStep adds a step to the workflow
func (w *Workflow) AddStep(stepType, agent string, payload map[string]interface{}, parallel bool, timeout time.Duration) {
	step := WorkflowStep{
		ID:       uuid.New().String(),
		Type:     stepType,
		Agent:    agent,
		Payload:  payload,
		Parallel: parallel,
		Timeout:  timeout,
	}
	w.Tasks = append(w.Tasks, step)
	w.UpdatedAt = time.Now()
}

// NewSchedule creates a new schedule instance
func NewSchedule(name, scheduleType, targetID, cron string, payload map[string]interface{}) *Schedule {
	now := time.Now()
	return &Schedule{
		ID:        uuid.New().String(),
		Name:      name,
		Type:      scheduleType,
		TargetID:  targetID,
		Cron:      cron,
		Enabled:   true,
		Payload:   payload,
		CreatedAt: now,
		UpdatedAt: now,
	}
}