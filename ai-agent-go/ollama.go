package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strings"
)

type OllamaClient struct {
	baseURL string
	model   string
	numCtx  int
	client  *http.Client
}

func NewOllamaClient(baseURL, model string, numCtx int) *OllamaClient {
	return &OllamaClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		model:   model,
		numCtx:  numCtx,
		client:  &http.Client{},
	}
}

func (c *OllamaClient) Close() error {
	return nil
}

func (c *OllamaClient) EnsureModelAvailable(model string) error {
	target := model
	if target == "" {
		target = c.model
	}
	response, err := c.client.Get(c.baseURL + "/api/tags")
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(response.Body)
		return fmt.Errorf("Ollama /api/tags returned %d: %s", response.StatusCode, strings.TrimSpace(string(body)))
	}
	var payload struct {
		Models []map[string]any `json:"models"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
		return err
	}
	available := map[string]bool{}
	for _, item := range payload.Models {
		name := fmt.Sprint(item["name"])
		if name == "" || name == "<nil>" {
			name = fmt.Sprint(item["model"])
		}
		if name != "" && name != "<nil>" {
			available[name] = true
		}
	}
	if !available[target] {
		modelNames := make([]string, 0, len(available))
		for name := range available {
			modelNames = append(modelNames, name)
		}
		sort.Strings(modelNames)
		availableText := "none"
		if len(modelNames) > 0 {
			availableText = strings.Join(modelNames, ", ")
		}
		return fmt.Errorf("Ollama model %q is not available. Available models: %s", target, availableText)
	}
	return nil
}

func (c *OllamaClient) Generate(prompt string) (string, error) {
	message, err := c.Chat([]Message{{Role: "user", Content: prompt}}, nil)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(message.Content), nil
}

func (c *OllamaClient) Chat(messages []Message, model *string) (Message, error) {
	target := c.model
	if model != nil && *model != "" {
		target = *model
	}
	payload := map[string]any{
		"model":    target,
		"messages": messages,
		"stream":   false,
	}
	if c.numCtx > 0 {
		payload["options"] = map[string]any{"num_ctx": c.numCtx}
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return Message{}, err
	}
	request, err := http.NewRequest(http.MethodPost, c.baseURL+"/api/chat", bytes.NewReader(body))
	if err != nil {
		return Message{}, err
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := c.client.Do(request)
	if err != nil {
		return Message{}, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(response.Body)
		text := strings.TrimSpace(string(body))
		if text != "" {
			return Message{}, fmt.Errorf("Ollama /api/chat returned %d: %s", response.StatusCode, text)
		}
		return Message{}, fmt.Errorf("Ollama /api/chat returned %d", response.StatusCode)
	}
	var payloadOut struct {
		Message Message `json:"message"`
	}
	if err := json.NewDecoder(response.Body).Decode(&payloadOut); err != nil {
		return Message{}, err
	}
	return payloadOut.Message, nil
}

func (c *OllamaClient) ResolveArgs(question, task, tool, toolSchema string, context map[int]StepResult) (map[string]any, error) {
	keys := make([]int, 0, len(context))
	for key := range context {
		keys = append(keys, key)
	}
	sort.Ints(keys)
	contextLines := make([]string, 0, len(keys))
	for _, key := range keys {
		contextLines = append(contextLines, fmt.Sprintf("Step %d: %s", key, context[key].Response))
	}
	contextText := "(none)"
	if len(contextLines) > 0 {
		contextText = strings.Join(contextLines, "\n")
	}
	prompt := strings.NewReplacer(
		"{question}", question,
		"{tool}", tool,
		"{tool_schema}", toolSchema,
		"{task}", task,
		"{context}", contextText,
	).Replace(argResolutionPrompt)
	raw, err := c.Generate(prompt)
	if err != nil {
		return map[string]any{}, err
	}
	parsed := parseJSONObject(raw)
	if parsed == nil {
		return map[string]any{}, nil
	}
	return normalizeToolArgs(parsed), nil
}

func (c *OllamaClient) SynthesizeAnswer(question string, steps []TrajectoryStep, plan Plan, history []Message) (string, error) {
	var b strings.Builder
	b.WriteString("You are a ThingsBoard operations assistant.\n")
	b.WriteString("Use the step outputs below to answer the question in plain text.\n")
	b.WriteString("Do not mention the plan structure or tool metadata.\n\n")
	b.WriteString("Question:\n")
	b.WriteString(question)
	b.WriteString("\n\nStep outputs:\n")
	for _, step := range steps {
		b.WriteString(fmt.Sprintf("Step %d [%s]: %s\n", step.Step, step.Action, step.Observation))
	}
	if len(history) > 0 {
		b.WriteString("\nConversation history:\n")
		b.WriteString(formatMessages(history))
		b.WriteString("\n")
	}
	message, err := c.Chat([]Message{{Role: "user", Content: b.String()}}, nil)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(message.Content), nil
}

const argResolutionPrompt = `Generate the JSON arguments for the tool call below.

Question: {question}
Tool: {tool}
Tool schema and guidance: {tool_schema}
Task: {task}

Prior step results:
{context}

YOUR RESPONSE MUST BE A SINGLE RAW JSON OBJECT AND NOTHING ELSE.
Do not write any explanation, reasoning, or prose — output only the JSON object.
Use EXACTLY the parameter names listed in "Tool schema and guidance" above.
Use the task description and prior step results to determine the correct argument values.
If a value comes from a list, use the first relevant element.
Omit optional parameters when no value is needed; do not output null or None.
For parameters whose names end in "Json", output a valid JSON document encoded
as a string, using any guide output in the prior step results when available.

JSON:`

func parseJSONObject(raw string) map[string]any {
	text := strings.TrimSpace(raw)
	if text == "" {
		return nil
	}
	if strings.HasPrefix(text, "```") {
		lines := strings.Split(text, "\n")
		if len(lines) > 1 {
			inner := lines[1:]
			if strings.TrimSpace(lines[len(lines)-1]) == "```" {
				inner = lines[1 : len(lines)-1]
			}
			text = strings.TrimSpace(strings.TrimPrefix(strings.Join(inner, "\n"), "json"))
		}
	}
	var result map[string]any
	if err := json.Unmarshal([]byte(text), &result); err == nil {
		return result
	}
	start := strings.Index(text, "{")
	end := strings.LastIndex(text, "}")
	if start >= 0 && end > start {
		if err := json.Unmarshal([]byte(text[start:end+1]), &result); err == nil {
			return result
		}
	}
	return nil
}

func normalizeToolArgs(args map[string]any) map[string]any {
	normalized := map[string]any{}
	for key, value := range args {
		if value == nil {
			continue
		}
		cleaned := normalizeArgValue(value)
		if strings.HasSuffix(key, "Json") {
			switch cleaned.(type) {
			case map[string]any, []any:
				if encoded, err := json.Marshal(cleaned); err == nil {
					cleaned = string(encoded)
				}
			}
		}
		normalized[key] = cleaned
	}
	return normalized
}

func normalizeArgValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		cleaned := map[string]any{}
		for key, item := range typed {
			if item == nil {
				continue
			}
			cleaned[key] = normalizeArgValue(item)
		}
		return cleaned
	case []any:
		cleaned := make([]any, 0, len(typed))
		for _, item := range typed {
			if item == nil {
				continue
			}
			cleaned = append(cleaned, normalizeArgValue(item))
		}
		return cleaned
	default:
		return value
	}
}
