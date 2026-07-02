package main

import (
	"os"
	"strconv"
)

type Settings struct {
	OllamaBaseURL       string
	OllamaModel         string
	OllamaNumCtx        int
	MCPServerURL        string
	MaxSteps            int
	MaxToolsPerQuery    int
	MaxAlarmPages       int
	MaxObservationChars int
	Port                int
}

func loadSettings() Settings {
	return Settings{
		OllamaBaseURL:       getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
		OllamaModel:         getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
		OllamaNumCtx:        getenvInt("OLLAMA_NUM_CTX", 1024),
		MCPServerURL:        getenv("MCP_SERVER_URL", getenv("MCP_SERVER_DEFAULT_URL", "http://thingsboard-mcp:8000/sse")),
		MaxSteps:            getenvInt("MAX_STEPS", 0),
		MaxToolsPerQuery:    getenvInt("MAX_TOOLS_PER_QUERY", 40),
		MaxAlarmPages:       getenvInt("MAX_ALARM_PAGES", 1),
		MaxObservationChars: getenvInt("MAX_OBSERVATION_CHARS", 4000),
		Port:                getenvInt("PORT", 8300),
	}
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}
