package agent

import (
	"context"
	"sync"
	"time"

	"github.com/agenticgen/orchestrator/internal/coordinator"
	"github.com/agenticgen/orchestrator/pkg/models"
	"github.com/sirupsen/logrus"
)

// Manager manages agent registration, health checks, and communication
type Manager struct {
	coordinator   *coordinator.Coordinator
	agents        map[string]*models.Agent
	activeAgents  map[string]*AgentConnection
	mu            sync.RWMutex
	ctx           context.Context
	cancel        context.CancelFunc
	healthChecker *HealthChecker
}

// AgentConnection represents an active agent connection
type AgentConnection struct {
	ID          string
	Conn        interface{} // WebSocket or gRPC connection
	LastSeen    time.Time
	Queue       chan *models.Task
	MaxQueue    int
	IsExecuting bool
}

// HealthChecker monitors agent health
type HealthChecker struct {
	agents map[string]*models.Agent
	mu     sync.RWMutex
}

// NewManager creates a new agent manager
func NewManager(coord *coordinator.Coordinator) *Manager {
	ctx, cancel := context.WithCancel(context.Background())

	return &Manager{
		coordinator:   coord,
		agents:        make(map[string]*models.Agent),
		activeAgents:  make(map[string]*AgentConnection),
		ctx:           ctx,
		cancel:        cancel,
		healthChecker: NewHealthChecker(),
	}
}

// Start begins the agent manager's main loop
func (m *Manager) Start(ctx context.Context) {
	logrus.Info("Starting agent manager")

	// Start health checker
	go m.healthChecker.Start(ctx)

	// Start connection monitor
	go m.monitorConnections()

	logrus.Info("Agent manager started")
}

// RegisterAgent registers a new agent
func (m *Manager) RegisterAgent(agent *models.Agent) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Set initial status
	agent.Status = models.AgentStatusIdle
	agent.LastSeen = time.Now()

	// Store agent
	m.agents[agent.ID] = agent

	// Create connection
	conn := &AgentConnection{
		ID:       agent.ID,
		Queue:    make(chan *models.Task, 100), // Queue of up to 100 tasks
		MaxQueue: 100,
		LastSeen: time.Now(),
	}

	m.activeAgents[agent.ID] = conn

	// Start agent worker
	go m.agentWorker(conn)

	logrus.WithFields(logrus.Fields{
		"agent_id": agent.ID,
		"name":     agent.Name,
		"type":     agent.Type,
	}).Info("Agent registered")

	return nil
}

// UnregisterAgent removes an agent from the system
func (m *Manager) UnregisterAgent(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	conn, exists := m.activeAgents[id]
	if !exists {
		return nil // Agent not found
	}

	// Close connection channel
	close(conn.Queue)

	// Remove from active agents
	delete(m.activeAgents, id)

	// Update agent status
	if agent, exists := m.agents[id]; exists {
		agent.Status = models.AgentStatusOffline
	}

	logrus.WithField("agent_id", id).Info("Agent unregistered")

	return nil
}

// AssignTask assigns a task to an agent
func (m *Manager) AssignTask(task *models.Task) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()

	conn, exists := m.activeAgents[task.AgentID]
	if !exists {
		return false
	}

	// Check if agent is available
	if conn.IsExecuting {
		return false
	}

	// Add task to queue
	select {
	case conn.Queue <- task:
		conn.IsExecuting = true
		return true
	default:
		// Queue is full
		return false
	}
}

// GetAvailableAgents returns a list of available agents
func (m *Manager) GetAvailableAgents() []*models.Agent {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var available []*models.Agent

	for _, agent := range m.agents {
		if agent.Status == models.AgentStatusIdle {
			available = append(available, agent)
		}
	}

	return available
}

// GetAgentsByType returns agents of a specific type
func (m *Manager) GetAgentsByType(agentType string) []*models.Agent {
	m.mu.RLock()
	defer m.mu.RUnlock()

	var agents []*models.Agent

	for _, agent := range m.agents {
		if agent.Type == agentType {
			agents = append(agents, agent)
		}
	}

	return agents
}

// UpdateAgentStatus updates an agent's status
func (m *Manager) UpdateAgentStatus(id string, status models.AgentStatus) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	agent, exists := m.agents[id]
	if !exists {
		return nil // Agent not found
	}

	agent.Status = status
	agent.LastSeen = time.Now()

	logrus.WithFields(logrus.Fields{
		"agent_id": id,
		"status":   status,
	}).Debug("Agent status updated")

	return nil
}

// agentWorker processes tasks for an agent
func (m *Manager) agentWorker(conn *AgentConnection) {
	logrus.WithField("agent_id", conn.ID).Debug("Starting agent worker")

	for {
		select {
		case task := <-conn.Queue:
			m.executeTask(conn, task)
		case <-m.ctx.Done():
			logrus.WithField("agent_id", conn.ID).Debug("Agent worker stopping")
			return
		}
	}
}

// executeTask executes a task and reports the result
func (m *Manager) executeTask(conn *AgentConnection, task *models.Task) {
	logrus.WithFields(logrus.Fields{
		"agent_id": conn.ID,
		"task_id":  task.ID,
	}).Info("Executing task")

	// Mark task as running
	task.Status = models.TaskStatusRunning
	now := time.Now()
	task.StartedAt = &now

	// Update agent status
	m.UpdateAgentStatus(conn.ID, models.AgentStatusBusy)

	// In a real implementation, this would:
	// 1. Send task to agent via WebSocket/gRPC
	// 2. Wait for response
	// 3. Process result

	// Simulate task execution
	time.Sleep(100 * time.Millisecond)

	// Mark task as completed
	task.Status = models.TaskStatusCompleted
	completedAt := time.Now()
	task.CompletedAt = &completedAt

	// Simulate result
	task.Result = map[string]interface{}{
		"status":    "success",
		"output":    "Task completed successfully",
		"duration": completedAt.Sub(*task.StartedAt).Milliseconds(),
	}

	// Report result to coordinator
	m.reportTaskResult(task)

	// Update agent status
	m.UpdateAgentStatus(conn.ID, models.AgentStatusIdle)

	// Mark as not executing
	conn.IsExecuting = false

	logrus.WithFields(logrus.Fields{
		"agent_id": conn.ID,
		"task_id":  task.ID,
		"status":   task.Status,
	}).Info("Task execution completed")
}

// reportTaskResult reports task completion to coordinator
func (m *Manager) reportTaskResult(task *models.Task) {
	// In a real implementation, this would send the result back to the coordinator
	logrus.WithFields(logrus.Fields{
		"task_id": task.ID,
		"status":  task.Status,
	}).Debug("Task result reported")
}

// monitorConnections monitors agent connections for health
func (m *Manager) monitorConnections() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			m.checkConnectionHealth()
		case <-m.ctx.Done():
			return
		}
	}
}

// checkConnectionHealth checks if agents are still connected
func (m *Manager) checkConnectionHealth() {
	m.mu.RLock()
	defer m.mu.RUnlock()

	now := time.Now()

	for id, conn := range m.activeAgents {
		// Check if agent hasn't been seen in 2 minutes
		if now.Sub(conn.LastSeen) > 2*time.Minute {
			logrus.WithField("agent_id", id).Warn("Agent connection timeout")

			// Mark as offline
			if agent, exists := m.agents[id]; exists {
				agent.Status = models.AgentStatusOffline
			}
		}
	}
}

// NewHealthChecker creates a new health checker
func NewHealthChecker() *HealthChecker {
	return &HealthChecker{
		agents: make(map[string]*models.Agent),
	}
}

// Start begins the health checker's main loop
func (h *HealthChecker) Start(ctx context.Context) {
	logrus.Info("Starting health checker")

	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			h.performHealthCheck()
		case <-ctx.Done():
			return
		}
	}
}

// performHealthCheck performs a health check on all agents
func (h *HealthChecker) performHealthCheck() {
	h.mu.RLock()
	defer h.mu.RUnlock()

	now := time.Now()

	for id, agent := range h.agents {
		// Check if agent is offline
		if agent.Status != models.AgentStatusOffline {
			if now.Sub(agent.LastSeen) > 5*time.Minute {
				logrus.WithField("agent_id", id).Warn("Agent appears to be offline")
				agent.Status = models.AgentStatusOffline
			}
		}
	}
}