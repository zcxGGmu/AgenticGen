package websocket

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"

	"github.com/agenticgen/orchestrator/internal/coordinator"
	"github.com/agenticgen/orchestrator/pkg/models"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/sirupsen/logrus"
)

// Gateway manages WebSocket connections for real-time communication
type Gateway struct {
	coordinator *coordinator.Coordinator
	upgrader    *websocket.Upgrader
	clients     map[string]*Client
	mu          sync.RWMutex
}

// Client represents a WebSocket client connection
type Client struct {
	ID        string
	Conn      *websocket.Conn
	Send      chan []byte
	AgentID   string
	Type      ClientType
	LastSeen  time.Time
}

// ClientType represents the type of client
type ClientType string

const (
	ClientTypeAgent   ClientType = "agent"
	ClientTypeUser    ClientType = "user"
	ClientTypeMonitor ClientType = "monitor"
)

// Message represents a WebSocket message
type Message struct {
	Type      string                 `json:"type"`
	Timestamp time.Time              `json:"timestamp"`
	Data      map[string]interface{} `json:"data"`
}

// NewGateway creates a new WebSocket gateway
func NewGateway(coord *coordinator.Coordinator) *Gateway {
	return &Gateway{
		coordinator: coord,
		upgrader: &websocket.Upgrader{
			ReadBufferSize:  1024,
			WriteBufferSize: 1024,
			CheckOrigin: func(r *http.Request) bool {
				return true // Allow all origins in development
			},
		},
		clients: make(map[string]*Client),
	}
}

// Start begins the WebSocket gateway
func (g *Gateway) Start(ctx context.Context) {
	logrus.Info("Starting WebSocket gateway")

	// Start cleanup routine
	go g.cleanup(ctx)

	logrus.Info("WebSocket gateway started")
}

// HandleWebSocket handles WebSocket connection requests
func (g *Gateway) HandleWebSocket(c *gin.Context) {
	// Upgrade HTTP connection to WebSocket
	conn, err := g.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		logrus.WithError(err).Error("WebSocket upgrade failed")
		return
	}

	// Create client
	clientID := generateClientID()
	client := &Client{
		ID:       clientID,
		Conn:     conn,
		Send:     make(chan []byte, 256),
		LastSeen: time.Now(),
	}

	// Register client
	g.registerClient(client)
	defer g.unregisterClient(client.ID)

	// Start reader and writer goroutines
	go g.readPump(client)
	go g.writePump(client)

	logrus.WithField("client_id", clientID).Info("WebSocket client connected")
}

// registerClient adds a new client to the registry
func (g *Gateway) registerClient(client *Client) {
	g.mu.Lock()
	defer g.mu.Unlock()

	g.clients[client.ID] = client

	// Send welcome message
	welcome := Message{
		Type:      "welcome",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"client_id": client.ID,
			"server":   "agentic-orchestrator",
		},
	}

	g.sendMessage(client, welcome)
}

// unregisterClient removes a client from the registry
func (g *Gateway) unregisterClient(clientID string) {
	g.mu.Lock()
	defer g.mu.Unlock()

	client, exists := g.clients[clientID]
	if !exists {
		return
	}

	close(client.Send)
	delete(g.clients, clientID)

	logrus.WithField("client_id", clientID).Info("WebSocket client disconnected")

	// If it's an agent, unregister from coordinator
	if client.Type == ClientTypeAgent && client.AgentID != "" {
		// Unregister agent
		_ = g.coordinator.UnregisterAgent(client.AgentID)
	}
}

// readPump reads messages from the WebSocket connection
func (g *Gateway) readPump(client *Client) {
	defer client.Conn.Close()

	// Set read deadline
	client.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	client.Conn.SetPongHandler(func(string) error {
		client.Conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		var msg Message
		err := client.Conn.ReadJSON(&msg)
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseAbnormalClosure) {
				logrus.WithError(err).Warn("WebSocket error")
			}
			break
		}

		// Update last seen
		client.LastSeen = time.Now()

		// Handle message
		g.handleMessage(client, msg)
	}
}

// writePump writes messages to the WebSocket connection
func (g *Gateway) writePump(client *Client) {
	ticker := time.NewTicker(54 * time.Second)
	defer func() {
		ticker.Stop()
		client.Conn.Close()
	}()

	for {
		select {
		case message, ok := <-client.Send:
			client.Conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				return
			}

			err := client.Conn.WriteMessage(websocket.TextMessage, message)
			if err != nil {
				return
			}

		case <-ticker.C:
			// Send ping
			err := client.Conn.WriteMessage(websocket.PingMessage, nil)
			if err != nil {
				return
			}
		}
	}
}

// handleMessage processes incoming WebSocket messages
func (g *Gateway) handleMessage(client *Client, msg Message) {
	logrus.WithFields(logrus.Fields{
		"client_id": client.ID,
		"type":       msg.Type,
	}).Debug("Received WebSocket message")

	switch msg.Type {
	case "agent.register":
		g.handleAgentRegistration(client, msg)
	case "agent.unregister":
		g.handleAgentUnregistration(client, msg)
	case "agent.heartbeat":
		g.handleAgentHeartbeat(client, msg)
	case "agent.task_result":
		g.handleTaskResult(client, msg)
	case "user.command":
		g.handleUserCommand(client, msg)
	default:
		logrus.WithField("type", msg.Type).Warn("Unknown message type")
	}
}

// handleAgentRegistration handles agent registration
func (g *Gateway) handleAgentRegistration(client *Client, msg Message) {
	data := msg.Data

	// Extract agent information
	agentData, ok := data["agent"].(map[string]interface{})
	if !ok {
		logrus.Error("Invalid agent registration data")
		return
	}

	agentID, _ := agentData["id"].(string)
	name, _ := agentData["name"].(string)
	agentType, _ := agentData["type"].(string)

	// Extract capabilities
	var capabilities []string
	if capsInterface, ok := agentData["capabilities"].([]interface{}); ok {
		for _, cap := range capsInterface {
			if capStr, ok := cap.(string); ok {
				capabilities = append(capabilities, capStr)
			}
		}
	}

	// Create agent
	agent := models.NewAgent(name, agentType, capabilities)
	agent.ID = agentID

	// Register with coordinator
	err := g.coordinator.RegisterAgent(agent)
	if err != nil {
		logrus.WithError(err).Error("Failed to register agent")
		return
	}

	// Update client info
	client.Type = ClientTypeAgent
	client.AgentID = agentID

	logrus.WithFields(logrus.Fields{
		"agent_id": agentID,
		"name":     name,
		"type":     agentType,
	}).Info("Agent registered via WebSocket")

	// Send registration confirmation
	response := Message{
		Type:      "agent.registered",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"agent_id": agentID,
			"status":   "registered",
		},
	}

	g.sendMessage(client, response)
}

// handleAgentUnregistration handles agent unregistration
func (g *Gateway) handleAgentUnregistration(client *Client, msg Message) {
	if client.Type != ClientTypeAgent || client.AgentID == "" {
		logrus.Warn("Unregistration from non-agent client")
		return
	}

	// Unregister from coordinator
	err := g.coordinator.UnregisterAgent(client.AgentID)
	if err != nil {
		logrus.WithError(err).Error("Failed to unregister agent")
	}

	logrus.WithField("agent_id", client.AgentID).Info("Agent unregistered via WebSocket")
}

// handleAgentHeartbeat handles agent heartbeat messages
func (g *Gateway) handleAgentHeartbeat(client *Client, msg Message) {
	if client.Type != ClientTypeAgent || client.AgentID == "" {
		return
	}

	// Update last seen
	client.LastSeen = time.Now()

	// Update agent status in coordinator
	err := g.coordinator.UpdateAgentStatus(client.AgentID, models.AgentStatusActive)
	if err != nil {
		logrus.WithError(err).Error("Failed to update agent status")
	}

	// Send heartbeat response
	response := Message{
		Type:      "agent.heartbeat_ack",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"timestamp": time.Now().Unix(),
		},
	}

	g.sendMessage(client, response)
}

// handleTaskResult handles task completion results
func (g *Gateway) handleTaskResult(client *Client, msg Message) {
	if client.Type != ClientTypeAgent || client.AgentID == "" {
		return
	}

	// Extract task result
	taskData, ok := msg.Data["task"].(map[string]interface{})
	if !ok {
		logrus.Error("Invalid task result data")
		return
	}

	taskID, _ := taskData["id"].(string)
	status, _ := taskData["status"].(string)
	result, _ := taskData["result"].(map[string]interface{})

	logrus.WithFields(logrus.Fields{
		"agent_id": client.AgentID,
		"task_id":  taskID,
		"status":   status,
	}).Info("Received task result from agent")

	// Update task in coordinator
	// This would typically update the task with the result
	_ = result
}

// handleUserCommand handles user commands
func (g *Gateway) handleUserCommand(client *Client, msg Message) {
	data := msg.Data

	command, _ := data["command"].(string)
	target, _ := data["target"].(string)

	logrus.WithFields(logrus.Fields{
		"command": command,
		"target":  target,
	}).Info("Received user command")

	// Handle different commands
	switch command {
	case "list_agents":
		g.sendAgentList(client)
	case "create_task":
		g.handleCreateTask(client, data)
	case "create_workflow":
		g.handleCreateWorkflow(client, data)
	default:
		logrus.WithField("command", command).Warn("Unknown command")
	}
}

// sendAgentList sends the list of agents to a client
func (g *Gateway) sendAgentList(client *Client) {
	// Get agents from coordinator
	agents := g.coordinator.GetAgents()

	response := Message{
		Type:      "user.agents",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"agents": agents,
		},
	}

	g.sendMessage(client, response)
}

// handleCreateTask creates a new task
func (g *Gateway) handleCreateTask(client *Client, data map[string]interface{}) {
	taskData, ok := data["task"].(map[string]interface{})
	if !ok {
		return
	}

	// Create task
	task := models.NewTask(
		taskData["agent_id"].(string),
		taskData["type"].(string),
		0,
		taskData,
	)

	// Submit to coordinator
	err := g.coordinator.CreateTask(context.Background(), task)
	if err != nil {
		logrus.WithError(err).Error("Failed to create task")
		return
	}

	response := Message{
		Type:      "user.task_created",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"task_id": task.ID,
			"status":  "created",
		},
	}

	g.sendMessage(client, response)
}

// handleCreateWorkflow creates a new workflow
func (g *Gateway) handleCreateWorkflow(client *Client, data map[string]interface{}) {
	workflowData, ok := data["workflow"].(map[string]interface{})
	if !ok {
		return
	}

	// Create workflow
	workflow := models.NewWorkflow(
		workflowData["name"].(string),
		workflowData["description"].(string),
	)

	// Submit to coordinator
	err := g.coordinator.CreateWorkflow(context.Background(), workflow)
	if err != nil {
		logrus.WithError(err).Error("Failed to create workflow")
		return
	}

	response := Message{
		Type:      "user.workflow_created",
		Timestamp: time.Now(),
		Data: map[string]interface{}{
			"workflow_id": workflow.ID,
			"status":      "created",
		},
	}

	g.sendMessage(client, response)
}

// sendMessage sends a message to a client
func (g *Gateway) sendMessage(client *Client, msg Message) {
	data, err := json.Marshal(msg)
	if err != nil {
		logrus.WithError(err).Error("Failed to marshal message")
		return
	}

	select {
	case client.Send <- data:
	default:
		// Channel is full, client is probably disconnected
		close(client.Send)
	}
}

// broadcast sends a message to all connected clients
func (g *Gateway) broadcast(msg Message) {
	g.mu.RLock()
	defer g.mu.RUnlock()

	for _, client := range g.clients {
		g.sendMessage(client, msg)
	}
}

// cleanup removes inactive clients
func (g *Gateway) cleanup(ctx context.Context) {
	ticker := time.NewTicker(60 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			g.cleanupClients()
		case <-ctx.Done():
			return
		}
	}
}

// cleanupClients removes clients that haven't sent a message in 5 minutes
func (g *Gateway) cleanupClients() {
	g.mu.Lock()
	defer g.mu.Unlock()

	now := time.Now()
	toRemove := []string{}

	for id, client := range g.clients {
		if now.Sub(client.LastSeen) > 5*time.Minute {
			toRemove = append(toRemove, id)
		}
	}

	for _, id := range toRemove {
		delete(g.clients, id)
		logrus.WithField("client_id", id).Info("Cleaned up inactive client")
	}
}

// generateClientID generates a unique client ID
func generateClientID() string {
	return fmt.Sprintf("client_%d", time.Now().UnixNano())
}