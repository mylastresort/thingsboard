package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

type TrajectoryStep struct {
	Step        int            `json:"step"`
	Action      string         `json:"action"`
	ActionInput map[string]any `json:"action_input,omitempty"`
	Observation string         `json:"observation"`
	ElapsedMs   int            `json:"elapsed_ms"`
}

type AgentResult struct {
	Answer            string          `json:"answer"`
	Status            string          `json:"status"`
	SessionID         *string         `json:"session_id,omitempty"`
	ToolCallingUsed   bool            `json:"tool_calling_used"`
	ToolCallingHeader string          `json:"tool_calling_header"`
	Trajectory        []TrajectoryStep `json:"trajectory"`
}

type ChatRequest struct {
	Message   string  `json:"message"`
	SessionID *string `json:"session_id,omitempty"`
	Model     *string `json:"model,omitempty"`
}

type RunRequest struct {
	Query  string         `json:"query"`
	Context map[string]any `json:"context,omitempty"`
	Model  *string        `json:"model,omitempty"`
}

type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type StepResult struct {
	Response string
}

type PlanStep struct {
	StepNumber     int
	Task           string
	Server         string
	Tool           string
	ToolArgs       map[string]any
	Dependencies   []int
	ExpectedOutput string
}

type Plan struct {
	Steps []PlanStep
	Raw   string
}

func (p Plan) GetStep(number int) *PlanStep {
	for i := range p.Steps {
		if p.Steps[i].StepNumber == number {
			return &p.Steps[i]
		}
	}
	return nil
}

func (p Plan) ResolvedOrder() []PlanStep {
	seen := map[int]bool{}
	ordered := make([]PlanStep, 0, len(p.Steps))
	var visit func(int)
	visit = func(number int) {
		if seen[number] {
			return
		}
		step := p.GetStep(number)
		if step == nil {
			return
		}
		for _, dep := range step.Dependencies {
			visit(dep)
		}
		seen[number] = true
		ordered = append(ordered, *step)
	}
	for _, step := range p.Steps {
		visit(step.StepNumber)
	}
	return ordered
}

func formatMessages(messages []Message) string {
	if len(messages) == 0 {
		return "(none)"
	}
	lines := make([]string, 0, len(messages))
	for _, message := range messages {
		content := strings.TrimSpace(message.Content)
		if content == "" {
			continue
		}
		lines = append(lines, fmt.Sprintf("%s: %s", message.Role, content))
	}
	if len(lines) == 0 {
		return "(none)"
	}
	return strings.Join(lines, "\n")
}

func prettyJSON(value any) string {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return fmt.Sprint(value)
	}
	return string(data)
}

func trimText(value string, maxChars int) string {
	if maxChars <= 0 || len(value) <= maxChars {
		return value
	}
	return value[:maxChars] + fmt.Sprintf("\n...[truncated %d chars]", len(value)-maxChars)
}

func lastObservation(steps []TrajectoryStep) string {
	if len(steps) == 0 {
		return ""
	}
	return steps[len(steps)-1].Observation
}

func resultForAnswer(answer, status string, trajectory []TrajectoryStep, sessionID string) AgentResult {
	return AgentResult{
		Answer:            answer,
		Status:            status,
		SessionID:         &sessionID,
		ToolCallingUsed:   false,
		ToolCallingHeader: "Tool Calling Not Used",
		Trajectory:        trajectory,
	}
}

func newID() string {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return strconv.FormatInt(int64(raw[0]), 10)
	}
	return hex.EncodeToString(raw[:])
}

func parseStepRefs(raw string) []int {
	parts := strings.Split(raw, ",")
	deps := make([]int, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" || strings.EqualFold(part, "none") {
			continue
		}
		part = strings.TrimPrefix(part, "#S")
		if number, err := strconv.Atoi(part); err == nil {
			deps = append(deps, number)
		}
	}
	return deps
}

func sortMapKeys(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
