package main

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"sync"

	gosdkmcp "github.com/modelcontextprotocol/go-sdk/mcp"
)

type McpClient struct {
	url     string
	client  *gosdkmcp.Client
	mu      sync.Mutex
	session *gosdkmcp.ClientSession
	tools   []McpTool
}

type McpTool struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"inputSchema"`
}

func NewMcpClient(url string) *McpClient {
	return &McpClient{
		url: url,
		client: gosdkmcp.NewClient(
			&gosdkmcp.Implementation{Name: "ai-agent", Version: "go"},
			nil,
		),
	}
}

func (c *McpClient) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.session != nil {
		err := c.session.Close()
		c.session = nil
		return err
	}
	return nil
}

func (c *McpClient) Connect(ctx context.Context) error {
	_, err := c.ensureSession(ctx)
	return err
}

func (c *McpClient) ensureSession(ctx context.Context) (*gosdkmcp.ClientSession, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.session != nil {
		return c.session, nil
	}
	transport := &gosdkmcp.SSEClientTransport{Endpoint: c.url}
	session, err := c.client.Connect(ctx, transport, nil)
	if err != nil {
		return nil, err
	}
	c.session = session
	return session, nil
}

func (c *McpClient) ListTools(ctx context.Context) ([]McpTool, error) {
	session, err := c.ensureSession(ctx)
	if err != nil {
		return nil, err
	}
	result, err := session.ListTools(ctx, nil)
	if err != nil {
		return nil, err
	}
	tools := make([]McpTool, 0, len(result.Tools))
	for _, tool := range result.Tools {
		tools = append(tools, toMcpTool(tool))
	}
	c.mu.Lock()
	c.tools = append([]McpTool(nil), tools...)
	c.mu.Unlock()
	return tools, nil
}

func (c *McpClient) CallTool(ctx context.Context, name string, arguments map[string]any) (string, error) {
	session, err := c.ensureSession(ctx)
	if err != nil {
		return "", err
	}
	result, err := session.CallTool(ctx, &gosdkmcp.CallToolParams{Name: name, Arguments: arguments})
	if err != nil {
		return "", err
	}
	return contentToText(result.Content), nil
}

func (c *McpClient) toolsSnapshot() []McpTool {
	c.mu.Lock()
	defer c.mu.Unlock()
	return append([]McpTool(nil), c.tools...)
}

func toMcpTool(tool *gosdkmcp.Tool) McpTool {
	if tool == nil {
		return McpTool{}
	}
	return McpTool{
		Name:        tool.Name,
		Description: tool.Description,
		InputSchema: toStringMap(tool.InputSchema),
	}
}

func toStringMap(value any) map[string]any {
	if value == nil {
		return map[string]any{}
	}
	if typed, ok := value.(map[string]any); ok {
		return typed
	}
	data, err := json.Marshal(value)
	if err != nil {
		return map[string]any{}
	}
	var out map[string]any
	if err := json.Unmarshal(data, &out); err != nil {
		return map[string]any{}
	}
	return out
}

func contentToText(content []gosdkmcp.Content) string {
	parts := make([]string, 0, len(content))
	for _, item := range content {
		switch typed := item.(type) {
		case *gosdkmcp.TextContent:
			parts = append(parts, typed.Text)
		default:
			data, err := json.Marshal(item)
			if err == nil {
				parts = append(parts, string(data))
			} else {
				parts = append(parts, fmt.Sprint(item))
			}
		}
	}
	return strings.Join(parts, "\n")
}