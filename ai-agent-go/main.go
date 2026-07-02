package main

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"sync"
	"syscall"
	"time"

	"google.golang.org/adk/agent"
)

type server struct {
	settings Settings
	mcp      *McpClient
	ollama   *OllamaClient
	agent    agent.Agent
	stateMu  sync.RWMutex
	ready    bool
	status   string
	lastErr  string
}

// func main() {
// 	tbAgent, err := buildAgent(
// 		os.Getenv("MCP_SERVER_URL"),
// 		os.Getenv("OLLAMA_BASE_URL"),
// 		os.Getenv("OLLAMA_MODEL"),
// 	)
// 	if err != nil {
// 		log.Fatalf("failed to create agent: %v", err)
// 	}

// 	config := &launcher.Config{AgentLoader: agent.NewSingleLoader(tbAgent)}
// 	l := full.NewLauncher()
// 	if err := l.Execute(context.Background(), config, os.Args[1:]); err != nil {
// 		log.Fatalf("run failed: %v\n\n%s", err, l.CommandLineSyntax())
// 	}
// }

func main() {
	settings := loadSettings()
	app := &server{
		settings: settings,
		mcp:      NewMcpClient(settings.MCPServerURL),
		ollama:   NewOllamaClient(settings.OllamaBaseURL, settings.OllamaModel, settings.OllamaNumCtx),
	}
	tbAgent, err := buildAgent(
		settings.MCPServerURL,
		settings.OllamaBaseURL,
		settings.OllamaModel,
	)
	if err != nil {
		log.Fatalf("failed to create agent: %v", err)
	}
	app.agent = tbAgent

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	mux := http.NewServeMux()
	registerRoutes(mux, app)

	httpServer := &http.Server{
		Addr:              fmt.Sprintf(":%d", settings.Port),
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		app.startupLoop(ctx)
	}()

	if len(os.Args) > 1 && os.Args[1] == "repl" {
		if err := app.waitUntilReady(ctx); err != nil {
			log.Fatal(err)
		}
		if err := app.runRepl(ctx); err != nil {
			log.Fatal(err)
		}
		return
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
	}()

	log.Printf("ai-agent listening on :%d", settings.Port)
	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatal(err)
	}
	_ = app.close()
}

func registerRoutes(mux *http.ServeMux, app *server) {
	mux.HandleFunc("/chat", app.chat)
	mux.HandleFunc("/chat/stream", app.chatStream)
	mux.HandleFunc("/run", app.run)
	mux.HandleFunc("/run/stream", app.runStream)
	mux.HandleFunc("/health", app.health)
}

func (s *server) startupLoop(ctx context.Context) {
	backoff := time.Second
	var lastLoggedErr string
	var lastLoggedAt time.Time
	for {
		if ctx.Err() != nil {
			return
		}
		s.setHealth("starting", false, "")
		if err := s.bootstrapOnce(ctx); err == nil {
			s.setHealth("ok", true, "")
			log.Printf("ai-agent ready: MCP=%s", s.settings.MCPServerURL)
			return
		} else {
			if err.Error() != lastLoggedErr || time.Since(lastLoggedAt) >= 30*time.Second {
				log.Printf("ai-agent startup waiting for dependencies: %v", err)
				lastLoggedErr = err.Error()
				lastLoggedAt = time.Now()
			}
			s.setHealth("starting", false, err.Error())
		}
		select {
		case <-time.After(backoff):
			if backoff < 15*time.Second {
				backoff *= 2
			}
		case <-ctx.Done():
			return
		}
	}
}

func (s *server) bootstrapOnce(ctx context.Context) error {
	if err := s.ollama.EnsureModelAvailable(s.settings.OllamaModel); err != nil {
		return err
	}
	if err := s.mcp.Connect(ctx); err != nil {
		return err
	}
	_, err := s.agent.RefreshTools(ctx)
	return err
}

func (s *server) waitUntilReady(ctx context.Context) error {
	ticker := time.NewTicker(200 * time.Millisecond)
	defer ticker.Stop()
	for {
		if s.isReady() {
			return nil
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (s *server) close() error {
	if err := s.ollama.Close(); err != nil {
		return err
	}
	return s.mcp.Close()
}

func (s *server) chat(w http.ResponseWriter, r *http.Request) {
	if !s.requireReady(w) {
		return
	}
	var request ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	model := request.Model
	if model != nil && *model != "" {
		if err := s.ollama.EnsureModelAvailable(*model); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	result, err := s.agent.RunAgent(r.Context(), request.Message, nil, model, request.SessionID, nil)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, result)
}

func (s *server) chatStream(w http.ResponseWriter, r *http.Request) {
	if !s.requireReady(w) {
		return
	}
	var request ChatRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.stream(w, func(progress func(TrajectoryStep)) (AgentResult, error) {
		model := request.Model
		if model != nil && *model != "" {
			if err := s.ollama.EnsureModelAvailable(*model); err != nil {
				return AgentResult{}, err
			}
		}
		return s.agent.RunAgent(r.Context(), request.Message, nil, model, request.SessionID, progress)
	})
}

func (s *server) run(w http.ResponseWriter, r *http.Request) {
	if !s.requireReady(w) {
		return
	}
	var request RunRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	model := request.Model
	if model != nil && *model != "" {
		if err := s.ollama.EnsureModelAvailable(*model); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
	}
	result, err := s.agent.RunAgent(r.Context(), request.Query, request.Context, model, nil, nil)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	writeJSON(w, result)
}

func (s *server) runStream(w http.ResponseWriter, r *http.Request) {
	if !s.requireReady(w) {
		return
	}
	var request RunRequest
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.stream(w, func(progress func(TrajectoryStep)) (AgentResult, error) {
		model := request.Model
		if model != nil && *model != "" {
			if err := s.ollama.EnsureModelAvailable(*model); err != nil {
				return AgentResult{}, err
			}
		}
		return s.agent.RunAgent(r.Context(), request.Query, request.Context, model, nil, progress)
	})
}

func (s *server) health(w http.ResponseWriter, _ *http.Request) {
	status, ready, lastErr := s.healthSnapshot()
	fmt.Printf("health check: status=%s, ready=%v, tool_count=%d, mcp_url=%s, error=%s\n", status, ready, len(s.agent.toolsSnapshot()), s.settings.MCPServerURL, lastErr)
	writeJSON(w, map[string]any{
		"status":     status,
		"ready":      ready,
		"tool_count": len(s.agent.toolsSnapshot()),
		"mcp_url":    s.settings.MCPServerURL,
		"error":      lastErr,
	})
}

func (s *server) stream(w http.ResponseWriter, run func(func(TrajectoryStep)) (AgentResult, error)) {
	w.Header().Set("Content-Type", "application/x-ndjson")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming unsupported", http.StatusInternalServerError)
		return
	}
	started := time.Now()
	encoder := json.NewEncoder(w)
	progress := func(step TrajectoryStep) {
		_ = encoder.Encode(map[string]any{"type": "step", "step": step})
		flusher.Flush()
	}
	result, err := run(progress)
	if err != nil {
		_ = encoder.Encode(map[string]any{"type": "error", "text": err.Error()})
		_ = encoder.Encode(map[string]any{"type": "done", "duration_ms": time.Since(started).Milliseconds()})
		flusher.Flush()
		return
	}
	_ = encoder.Encode(map[string]any{"type": "result", "result": result})
	_ = encoder.Encode(map[string]any{"type": "done", "duration_ms": time.Since(started).Milliseconds()})
	flusher.Flush()
}

func (s *server) setHealth(status string, ready bool, lastErr string) {
	s.stateMu.Lock()
	defer s.stateMu.Unlock()
	s.status = status
	s.ready = ready
	s.lastErr = lastErr
}

func (s *server) healthSnapshot() (string, bool, string) {
	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	return s.status, s.ready, s.lastErr
}

func (s *server) isReady() bool {
	s.stateMu.RLock()
	defer s.stateMu.RUnlock()
	return s.ready
}

func (s *server) requireReady(w http.ResponseWriter) bool {
	if s.isReady() {
		return true
	}
	status, _, lastErr := s.healthSnapshot()
	message := "ai-agent is not ready yet; check /health"
	if lastErr != "" {
		message = fmt.Sprintf("%s (status=%s, error=%s)", message, status, lastErr)
	}
	http.Error(w, message, http.StatusServiceUnavailable)
	return false
}

func (s *server) runRepl(ctx context.Context) error {
	sessionID := newID()
	fmt.Printf("ai-agent session: %s\n", sessionID)
	fmt.Println("Ctrl-D or empty line to exit.")
	reader := bufio.NewReader(os.Stdin)
	for {
		fmt.Print("> ")
		line, err := reader.ReadString('\n')
		if err != nil && strings.TrimSpace(line) == "" {
			return nil
		}
		query := strings.TrimSpace(line)
		if query == "" {
			return nil
		}
		fmt.Println("working...")
		invCtx := agent.InvocationContext{
			
		}
		result := s.agent.Run(invCtx)

		if err != nil {
			return err
		}
		sessionID = derefString(result.SessionID, sessionID)
		for _, step := range result.Trajectory {
			fmt.Printf("[%d] %s\n", step.Step, step.Action)
			if step.Observation != "" {
				fmt.Println(step.Observation)
			}
		}
		fmt.Println(result.Answer)
	}
}

func writeJSON(w http.ResponseWriter, payload any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(payload)
}

func derefString(value *string, fallback string) string {
	if value == nil || *value == "" {
		return fallback
	}
	return *value
}
