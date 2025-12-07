package coordinator

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"time"

	"github.com/agenticgen/orchestrator/pkg/models"
	"github.com/gin-gonic/gin"
	"github.com/sirupsen/logrus"
)

// Coordinator manages agents, tasks, and workflows
type Coordinator struct {
	agents    map[string]*models.Agent
	tasks     map[string]*models.Task
	workflows map[string]*models.Workflow
	schedules map[string]*models.Schedule
	mu        sync.RWMutex

	// Channels for communication
	taskChan    chan *models.Task
	resultChan  chan *models.Task
	agentChan   chan *models.Agent
	eventChan   chan *models.Event

	// Context for graceful shutdown
	ctx    context.Context
	cancel context.CancelFunc
}

// Event represents a system event
type Event struct {
	Type      string                 `json:"type"`
	Timestamp time.Time              `json:"timestamp"`
	Data      map[string]interface{} `json:"data"`
}

// NewCoordinator creates a new coordinator instance
func NewCoordinator() *Coordinator {
	ctx, cancel := context.WithCancel(context.Background())

	return &Coordinator{
		agents:    make(map[string]*models.Agent),
		tasks:     make(map[string]*models.Task),
		workflows: make(map[string]*models.Workflow),
		schedules: make(map[string]*models.Schedule),

		taskChan:   make(chan *models.Task, 1000),
		resultChan: make(chan *models.Task, 1000),
		agentChan:  make(chan *models.Agent, 100),
		eventChan:  make(chan *models.Event, 1000),

		ctx:    ctx,
		cancel: cancel,
	}
}

// Start begins the coordinator's main loop
func (c *Coordinator) Start(ctx context.Context) {
	logrus.Info("Starting coordinator")

	// Start processing loops
	go c.processTasks()
	go c.processResults()
	go c.processAgents()
	go c.processEvents()
	go c.cleanupExpiredTasks()

	// Emit startup event
	c.emitEvent("coordinator.started", map[string]interface{}{
		"timestamp": time.Now(),
	})

	// Wait for context cancellation
	<-ctx.Done()
	logrus.Info("Coordinator stopped")
}

// processTasks handles incoming tasks
func (c *Coordinator) processTasks() {
	for {
		select {
		case task := <-c.taskChan:
			c.assignTask(task)
		case <-c.ctx.Done():
			return
		}
	}
}

// processResults handles task completion results
func (c *Coordinator) processResults() {
	for {
		select {
		case task := <-c.resultChan:
			c.completeTask(task)
		case <-c.ctx.Done():
			return
		}
	}
}

// processAgents handles agent updates
func (c *Coordinator) processAgents() {
	for {
		select {
		case agent := <-c.agentChan:
			c.updateAgent(agent)
		case <-c.ctx.Done():
			return
		}
	}
}

// processEvents handles system events
func (c *Coordinator) processEvents() {
	for {
		select {
		case event := <-c.eventChan:
			c.handleEvent(event)
		case <-c.ctx.Done():
			return
		}
	}
}

// cleanupExpiredTasks removes tasks that have timed out
func (c *Coordinator) cleanupExpiredTasks() {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			c.checkTaskTimeouts()
		case <-c.ctx.Done():
			return
		}
	}
}

// assignTask assigns a task to an appropriate agent
func (c *Coordinator) assignTask(task *models.Task) {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Store the task
	c.tasks[task.ID] = task
	task.Status = models.TaskStatusPending
	task.CreatedAt = time.Now()

	// Find available agent
	agent := c.findAvailableAgent(task)
	if agent == nil {
		logrus.WithFields(logrus.Fields{
			"task_id": task.ID,
			"type":    task.Type,
		}).Warn("No available agent for task")
		return
	}

	// Assign task to agent
	task.AgentID = agent.ID
	task.Status = models.TaskStatusRunning
	now := time.Now()
	task.StartedAt = &now

	agent.Status = models.AgentStatusBusy
	agent.LastSeen = now

	logrus.WithFields(logrus.Fields{
		"task_id":  task.ID,
		"agent_id": agent.ID,
		"type":     task.Type,
	}).Info("Task assigned to agent")

	// Emit task assigned event
	c.emitEvent("task.assigned", map[string]interface{}{
		"task_id":  task.ID,
		"agent_id": agent.ID,
	})
}

// completeTask marks a task as completed
func (c *Coordinator) completeTask(task *models.Task) {
	c.mu.Lock()
	defer c.mu.Unlock()

	// Update task
	task.Status = models.TaskStatusCompleted
	now := time.Now()
	task.CompletedAt = &now

	// Update agent status
	if agent, exists := c.agents[task.AgentID]; exists {
		agent.Status = models.AgentStatusIdle
		agent.LastSeen = now
	}

	logrus.WithFields(logrus.Fields{
		"task_id":  task.ID,
		"agent_id": task.AgentID,
		"status":   task.Status,
	}).Info("Task completed")

	// Emit task completed event
	c.emitEvent("task.completed", map[string]interface{}{
		"task_id":  task.ID,
		"agent_id": task.AgentID,
		"result":   task.Result,
	})
}

// findAvailableAgent finds an agent capable of handling the task
func (c *Coordinator) findAvailableAgent(task *models.Task) *models.Agent {
	for _, agent := range c.agents {
		if agent.Status == models.AgentStatusIdle {
			// Check if agent has the required capability
			for _, capability := range agent.Capabilities {
				if capability == task.Type {
					return agent
				}
			}
		}
	}
	return nil
}

// updateAgent updates agent information
func (c *Coordinator) updateAgent(agent *models.Agent) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if existing, exists := c.agents[agent.ID]; exists {
		existing.Status = agent.Status
		existing.LastSeen = time.Now()
		existing.UpdatedAt = time.Now()
	}
}

// handleEvent processes system events
func (c *Coordinator) handleEvent(event *models.Event) {
	logrus.WithFields(logrus.Fields{
		"event_type": event.Type,
		"timestamp":  event.Timestamp,
	}).Debug("Processing event")

	// Handle different event types
	switch event.Type {
	case "task.assigned":
		// Task assignment logic
	case "task.completed":
		// Task completion logic
		// Check for workflow continuation
	case "agent.registered":
		// Agent registration logic
	case "agent.unregistered":
		// Agent unregistration logic
	}
}

// checkTaskTimeouts checks for timed out tasks
func (c *Coordinator) checkTaskTimeouts() {
	c.mu.RLock()
	defer c.mu.RUnlock()

	now := time.Now()

	for _, task := range c.tasks {
		if task.Status == models.TaskStatusRunning && task.StartedAt != nil {
			elapsed := now.Sub(*task.StartedAt)
			if elapsed > task.Timeout {
				logrus.WithFields(logrus.Fields{
					"task_id": task.ID,
					"elapsed": elapsed,
					"timeout": task.Timeout,
				}).Warn("Task timed out")

				// Mark task as timed out
				task.Status = models.TaskStatusTimeout
				task.Error = "Task execution timed out"
				task.CompletedAt = &now

				// Update agent status
				if agent, exists := c.agents[task.AgentID]; exists {
					agent.Status = models.AgentStatusIdle
				}

				// Emit timeout event
				c.emitEvent("task.timeout", map[string]interface{}{
					"task_id": task.ID,
				})
			}
		}
	}
}

// emitEvent emits a system event
func (c *Coordinator) emitEvent(eventType string, data map[string]interface{}) {
	event := &models.Event{
		Type:      eventType,
		Timestamp: time.Now(),
		Data:      data,
	}

	select {
	case c.eventChan <- event:
	default:
		logrus.Warn("Event channel full, dropping event")
	}
}

// HTTP Handlers

// CreateAgent handles agent creation
func (c *Coordinator) CreateAgent(ctx *gin.Context) {
	var agent models.Agent
	if err := ctx.ShouldBindJSON(&agent); err != nil {
		ctx.JSON(400, gin.H{"error": err.Error()})
		return
	}

	// Generate ID if not provided
	if agent.ID == "" {
		agent.CreatedAt = time.Now()
		agent.UpdatedAt = time.Now()
	}

	c.mu.Lock()
	c.agents[agent.ID] = &agent
	c.mu.Unlock()

	ctx.JSON(201, agent)
}

// ListAgents returns all agents
func (c *Coordinator) ListAgents(ctx *gin.Context) {
	c.mu.RLock()
	agents := make([]*models.Agent, 0, len(c.agents))
	for _, agent := range c.agents {
		agents = append(agents, agent)
	}
	c.mu.RUnlock()

	ctx.JSON(200, agents)
}

// GetAgent returns a specific agent
func (c *Coordinator) GetAgent(ctx *gin.Context) {
	id := ctx.Param("id")

	c.mu.RLock()
	agent, exists := c.agents[id]
	c.mu.RUnlock()

	if !exists {
		ctx.JSON(404, gin.H{"error": "Agent not found"})
		return
	}

	ctx.JSON(200, agent)
}

// CreateTask handles task creation
func (c *Coordinator) CreateTask(ctx *gin.Context) {
	var task models.Task
	if err := ctx.ShouldBindJSON(&task); err != nil {
		ctx.JSON(400, gin.H{"error": err.Error()})
		return
	}

	// Queue the task for assignment
	c.taskChan <- &task

	ctx.JSON(201, task)
}

// ListTasks returns all tasks
func (c *Coordinator) ListTasks(ctx *gin.Context) {
	c.mu.RLock()
	tasks := make([]*models.Task, 0, len(c.tasks))
	for _, task := range c.tasks {
		tasks = append(tasks, task)
	}
	c.mu.RUnlock()

	ctx.JSON(200, tasks)
}

// GetTask returns a specific task
func (c *Coordinator) GetTask(ctx *gin.Context) {
	id := ctx.Param("id")

	c.mu.RLock()
	task, exists := c.tasks[id]
	c.mu.RUnlock()

	if !exists {
		ctx.JSON(404, gin.H{"error": "Task not found"})
		return
	}

	ctx.JSON(200, task)
}

// CreateWorkflow handles workflow creation
func (c *Coordinator) CreateWorkflow(ctx *gin.Context) {
	var workflow models.Workflow
	if err := ctx.ShouldBindJSON(&workflow); err != nil {
		ctx.JSON(400, gin.H{"error": err.Error()})
		return
	}

	c.mu.Lock()
	c.workflows[workflow.ID] = &workflow
	c.mu.Unlock()

	ctx.JSON(201, workflow)
}

// ListWorkflows returns all workflows
func (c *Coordinator) ListWorkflows(ctx *gin.Context) {
	c.mu.RLock()
	workflows := make([]*models.Workflow, 0, len(c.workflows))
	for _, workflow := range c.workflows {
		workflows = append(workflows, workflow)
	}
	c.mu.RUnlock()

	ctx.JSON(200, workflows)
}

// GetWorkflow returns a specific workflow
func (c *Coordinator) GetWorkflow(ctx *gin.Context) {
	id := ctx.Param("id")

	c.mu.RLock()
	workflow, exists := c.workflows[id]
	c.mu.RUnlock()

	if !exists {
		ctx.JSON(404, gin.H{"error": "Workflow not found"})
		return
	}

	ctx.JSON(200, workflow)
}

// ExecuteWorkflow starts execution of a workflow
func (c *Coordinator) ExecuteWorkflow(ctx *gin.Context) {
	id := ctx.Param("id")

	c.mu.RLock()
	workflow, exists := c.workflows[id]
	c.mu.RUnlock()

	if !exists {
		ctx.JSON(404, gin.H{"error": "Workflow not found"})
		return
	}

	// Create tasks from workflow steps
	for _, step := range workflow.Tasks {
		task := models.NewTask(step.Agent, step.Type, 0, step.Payload)
		task.WorkflowID = workflow.ID
		c.taskChan <- task
	}

	// Update workflow status
	c.mu.Lock()
	workflow.Status = models.WorkflowStatusActive
	c.mu.Unlock()

	ctx.JSON(200, gin.H{"status": "started"})
}