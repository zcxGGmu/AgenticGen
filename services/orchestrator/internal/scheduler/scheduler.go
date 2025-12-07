package scheduler

import (
	"context"
	"sync"
	"time"

	"github.com/agenticgen/orchestrator/internal/coordinator"
	"github.com/agenticgen/orchestrator/pkg/models"
	"github.com/robfig/cron/v3"
	"github.com/sirupsen/logrus"
)

// Scheduler manages scheduled tasks and workflows
type Scheduler struct {
	coordinator *coordinator.Coordinator
	cron        *cron.Cron
	schedules   map[string]*models.Schedule
	mu          sync.RWMutex
	ctx         context.Context
	cancel      context.CancelFunc
}

// NewScheduler creates a new scheduler instance
func NewScheduler(coord *coordinator.Coordinator) *Scheduler {
	ctx, cancel := context.WithCancel(context.Background())

	return &Scheduler{
		coordinator: coord,
		cron:        cron.New(cron.WithSeconds()), // Support second-level precision
		schedules:   make(map[string]*models.Schedule),
		ctx:         ctx,
		cancel:      cancel,
	}
}

// Start begins the scheduler's main loop
func (s *Scheduler) Start(ctx context.Context) {
	logrus.Info("Starting scheduler")

	// Start cron scheduler
	s.cron.Start()

	// Load existing schedules
	s.loadSchedules()

	// Emit startup event
	logrus.Info("Scheduler started")

	// Wait for context cancellation
	<-ctx.Done()

	// Shutdown
	logrus.Info("Shutting down scheduler")
	s.cron.Stop()
	s.cancel()
}

// AddSchedule adds a new scheduled task or workflow
func (s *Scheduler) AddSchedule(schedule *models.Schedule) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Parse cron expression
	_, err := cron.ParseStandard(schedule.Cron)
	if err != nil {
		logrus.WithError(err).Error("Invalid cron expression")
		return err
	}

	// Store schedule
	s.schedules[schedule.ID] = schedule

	// Add to cron scheduler
	entryID, err := s.cron.AddFunc(schedule.Cron, func() {
		s.executeSchedule(schedule)
	})
	if err != nil {
		logrus.WithError(err).Error("Failed to add schedule to cron")
		return err
	}

	logrus.WithFields(logrus.Fields{
		"schedule_id": schedule.ID,
		"name":        schedule.Name,
		"cron":        schedule.Cron,
		"entry_id":    entryID,
	}).Info("Schedule added")

	return nil
}

// RemoveSchedule removes a scheduled task or workflow
func (s *Scheduler) RemoveSchedule(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	schedule, exists := s.schedules[id]
	if !exists {
		return nil // Already removed or doesn't exist
	}

	// Remove from cron scheduler
	err := s.cron.Remove(schedule.ID)
	if err != nil {
		logrus.WithError(err).Error("Failed to remove schedule from cron")
		return err
	}

	// Remove from storage
	delete(s.schedules, id)

	logrus.WithFields(logrus.Fields{
		"schedule_id": id,
		"name":        schedule.Name,
	}).Info("Schedule removed")

	return nil
}

// executeSchedule executes a scheduled task or workflow
func (s *Scheduler) executeSchedule(schedule *models.Schedule) {
	logrus.WithFields(logrus.Fields{
		"schedule_id": schedule.ID,
		"name":        schedule.Name,
		"type":        schedule.Type,
	}).Info("Executing schedule")

	now := time.Now()

	// Update last run time
	schedule.LastRun = &now

	// Calculate next run time
	nextRun := s.calculateNextRun(schedule.Cron, now)
	schedule.NextRun = &nextRun

	switch schedule.Type {
	case "task":
		s.executeScheduledTask(schedule)
	case "workflow":
		s.executeScheduledWorkflow(schedule)
	default:
		logrus.WithField("type", schedule.Type).Error("Unknown schedule type")
	}

	// Save updated schedule
	s.schedules[schedule.ID] = schedule
}

// executeScheduledTask creates and executes a task
func (s *Scheduler) executeScheduledTask(schedule *models.Schedule) {
	// Extract task details from payload
	payload, ok := schedule.Payload["task"].(map[string]interface{})
	if !ok {
		logrus.Error("Invalid task payload in schedule")
		return
	}

	// Create task
	taskType, _ := payload["type"].(string)
	agentID, _ := payload["agent_id"].(string)
	priority, _ := payload["priority"].(int)
	if priority == 0 {
		priority = 1 // Default priority
	}

	task := models.NewTask(agentID, taskType, priority, payload)
	task.CreatedAt = time.Now()

	// Submit task to coordinator
	// This would typically be done via a channel or direct call
	logrus.WithFields(logrus.Fields{
		"task_id": task.ID,
		"type":    task.Type,
	}).Info("Created scheduled task")
}

// executeScheduledWorkflow creates and executes a workflow
func (s *Scheduler) executeScheduledWorkflow(schedule *models.Schedule) {
	// Extract workflow details from payload
	payload, ok := schedule.Payload["workflow"].(map[string]interface{})
	if !ok {
		logrus.Error("Invalid workflow payload in schedule")
		return
	}

	// Create workflow
	name, _ := payload["name"].(string)
	description, _ := payload["description"].(string)
	workflow := models.NewWorkflow(name, description)

	// Add workflow steps
	if steps, ok := payload["steps"].([]interface{}); ok {
		for _, step := range steps {
			if stepMap, ok := step.(map[string]interface{}); ok {
				stepType, _ := stepMap["type"].(string)
				agent, _ := stepMap["agent"].(string)
				stepPayload, _ := stepMap["payload"].(map[string]interface{})
				parallel, _ := stepMap["parallel"].(bool)
				timeout := time.Duration(30) * time.Second // Default timeout

				if timeoutSec, ok := stepMap["timeout"].(float64); ok {
					timeout = time.Duration(timeoutSec) * time.Second
				}

				workflow.AddStep(stepType, agent, stepPayload, parallel, timeout)
			}
		}
	}

	// Submit workflow to coordinator
	logrus.WithFields(logrus.Fields{
		"workflow_id": workflow.ID,
		"name":        workflow.Name,
	}).Info("Created scheduled workflow")
}

// calculateNextRun calculates the next run time based on cron expression
func (s *Scheduler) calculateNextRun(cronExpr string, from time.Time) time.Time {
	parser := cron.NewParser(cron.Second | cron.Minute | cron.Hour | cron.Dom | cron.Month | cron.Dow)
	schedule, err := parser.Parse(cronExpr)
	if err != nil {
		logrus.WithError(err).Error("Failed to parse cron expression")
		return from.Add(24 * time.Hour) // Fallback to next day
	}

	return schedule.Next(from)
}

// loadSchedules loads existing schedules from storage
func (s *Scheduler) loadSchedules() {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// In a real implementation, this would load from a database
	// For now, we'll just log
	logrus.WithField("count", len(s.schedules)).Info("Loaded schedules")
}

// GetSchedules returns all schedules
func (s *Scheduler) GetSchedules() map[string]*models.Schedule {
	s.mu.RLock()
	defer s.mu.RUnlock()

	// Create a copy to avoid concurrent access issues
	schedules := make(map[string]*models.Schedule)
	for id, schedule := range s.schedules {
		// Create a copy of the schedule
		scheduleCopy := *schedule
		schedules[id] = &scheduleCopy
	}

	return schedules
}

// GetSchedule returns a specific schedule
func (s *Scheduler) GetSchedule(id string) (*models.Schedule, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	schedule, exists := s.schedules[id]
	if !exists {
		return nil, false
	}

	// Return a copy
	scheduleCopy := *schedule
	return &scheduleCopy, true
}

// UpdateSchedule updates an existing schedule
func (s *Scheduler) UpdateSchedule(schedule *models.Schedule) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	// Check if schedule exists
	_, exists := s.schedules[schedule.ID]
	if !exists {
		return nil // Schedule doesn't exist
	}

	// Remove old cron job
	s.cron.Remove(schedule.ID)

	// Add new cron job if enabled
	if schedule.Enabled {
		_, err := s.cron.AddFunc(schedule.Cron, func() {
			s.executeSchedule(schedule)
		})
		if err != nil {
			return err
		}
	}

	// Update schedule
	s.schedules[schedule.ID] = schedule

	logrus.WithFields(logrus.Fields{
		"schedule_id": schedule.ID,
		"enabled":     schedule.Enabled,
	}).Info("Schedule updated")

	return nil
}