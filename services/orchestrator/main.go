package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/agenticgen/orchestrator/internal/agent"
	"github.com/agenticgen/orchestrator/internal/coordinator"
	"github.com/agenticgen/orchestrator/internal/scheduler"
	"github.com/agenticgen/orchestrator/internal/websocket"
	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"
	"github.com/sirupsen/logrus"
	"google.golang.org/grpc"
)

func main() {
	// Setup logging
	logrus.SetLevel(logrus.InfoLevel)
	logrus.SetFormatter(&logrus.JSONFormatter{})

	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Initialize coordinator
	coord := coordinator.NewCoordinator()
	go coord.Start(ctx)

	// Initialize scheduler
	sched := scheduler.NewScheduler(coord)
	go sched.Start(ctx)

	// Initialize agent manager
	agentMgr := agent.NewManager(coord)
	go agentMgr.Start(ctx)

	// Setup WebSocket gateway
	wsGateway := websocket.NewGateway(coord)
	go wsGateway.Start(ctx)

	// Setup HTTP server
	router := gin.New()
	setupRoutes(router, coord, wsGateway)

	// Setup gRPC server
	grpcServer := grpc.NewServer()
	setupGRPC(grpcServer, coord)

	// Start servers
	httpPort := os.Getenv("HTTP_PORT")
	if httpPort == "" {
		httpPort = "8080"
	}

	grpcPort := os.Getenv("GRPC_PORT")
	if grpcPort == "" {
		grpcPort = "9090"
	}

	// Start HTTP server
	httpServer := &http.Server{
		Addr:    ":" + httpPort,
		Handler: router,
	}

	go func() {
		logrus.WithField("port", httpPort).Info("Starting HTTP server")
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logrus.WithError(err).Fatal("HTTP server failed")
		}
	}()

	// Start gRPC server
	lis, err := net.Listen("tcp", ":"+grpcPort)
	if err != nil {
		logrus.WithError(err).Fatal("Failed to listen for gRPC")
	}

	go func() {
		logrus.WithField("port", grpcPort).Info("Starting gRPC server")
		if err := grpcServer.Serve(lis); err != nil {
			logrus.WithError(err).Error("gRPC server error")
		}
	}()

	// Setup graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	<-sigChan
	logrus.Info("Shutting down gracefully...")

	// Shutdown servers
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutdownCancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		logrus.WithError(err).Error("HTTP server shutdown error")
	}

	grpcServer.GracefulStop()
	cancel()

	logrus.Info("Shutdown complete")
}

func setupRoutes(router *gin.Engine, coord *coordinator.Coordinator, wsGateway *websocket.Gateway) {
	// Health check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{
			"status": "healthy",
			"time":   time.Now().UTC(),
		})
	})

	// Metrics endpoint
	router.GET("/metrics", gin.WrapH(promhttp.Handler()))

	// WebSocket endpoint
	router.GET("/ws", wsGateway.HandleWebSocket)

	// API routes
	v1 := router.Group("/api/v1")
	{
		// Agent management
		v1.POST("/agents", coord.CreateAgent)
		v1.GET("/agents", coord.ListAgents)
		v1.GET("/agents/:id", coord.GetAgent)
		v1.PUT("/agents/:id", coord.UpdateAgent)
		v1.DELETE("/agents/:id", coord.DeleteAgent)

		// Task management
		v1.POST("/tasks", coord.CreateTask)
		v1.GET("/tasks", coord.ListTasks)
		v1.GET("/tasks/:id", coord.GetTask)
		v1.PUT("/tasks/:id", coord.UpdateTask)
		v1.DELETE("/tasks/:id", coord.DeleteTask)

		// Workflow management
		v1.POST("/workflows", coord.CreateWorkflow)
		v1.GET("/workflows", coord.ListWorkflows)
		v1.GET("/workflows/:id", coord.GetWorkflow)
		v1.POST("/workflows/:id/execute", coord.ExecuteWorkflow)

		// Scheduler management
		v1.POST("/schedules", coord.CreateSchedule)
		v1.GET("/schedules", coord.ListSchedules)
		v1.DELETE("/schedules/:id", coord.DeleteSchedule)
	}
}

func setupGRPC(server *grpc.Server, coord *coordinator.Coordinator) {
	// Register gRPC services here
	// orchestration.RegisterOrchestrationServer(server, coord)
}