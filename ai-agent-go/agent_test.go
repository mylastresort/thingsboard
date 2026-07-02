package main

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

type fakeMCPClient struct {
	tools     []McpTool
	responses []string
	calls     []fakeMCPCall
}

type fakeMCPCall struct {
	name      string
	arguments map[string]any
}

func (f *fakeMCPClient) ListTools(ctx context.Context) ([]McpTool, error) {
	_ = ctx
	return append([]McpTool(nil), f.tools...), nil
}

func (f *fakeMCPClient) CallTool(ctx context.Context, name string, arguments map[string]any) (string, error) {
	_ = ctx
	copiedArguments := make(map[string]any, len(arguments))
	for key, value := range arguments {
		copiedArguments[key] = value
	}
	f.calls = append(f.calls, fakeMCPCall{name: name, arguments: copiedArguments})
	if len(f.responses) == 0 {
		return "", errors.New("no fake MCP response")
	}
	response := f.responses[0]
	f.responses = f.responses[1:]
	return response, nil
}

func TestSummarizeLiveDevices(t *testing.T) {
	rawResult := `{
		"data": [
			{
				"entityId": {"entityType": "DEVICE", "id": "abc-1"},
				"latest": {
					"ENTITY_FIELD": {
						"name": {"value": "Sensor A"},
						"label": {"value": "Building 1"}
					}
				}
			},
			{
				"entityId": {"entityType": "DEVICE", "id": "abc-2"},
				"latest": {
					"ENTITY_FIELD": {
						"name": {"value": "Sensor B"}
					}
				}
			}
		]
	}`

	got := summarizeLiveDevices(rawResult)
	want := "Live devices currently available:\n- Sensor A (Building 1)\n- Sensor B"
	if got != want {
		t.Fatalf("unexpected summary\nwant: %s\n got: %s", want, got)
	}
}

func TestIsLiveAlarmQuery(t *testing.T) {
	if !isLiveAlarmQuery("list live alarms in thingsboard") {
		t.Fatal("expected live alarm query to be detected")
	}
	if isLiveAlarmQuery("list alarms in thingsboard") {
		t.Fatal("expected non-live alarm query to be rejected")
	}
}

func TestSummarizeLiveAlarms(t *testing.T) {
	oldLocal := time.Local
	time.Local = time.UTC
	defer func() { time.Local = oldLocal }()

	alarm := map[string]any{
		"type":           "Overheat",
		"severity":       "MAJOR",
		"status":         "ACTIVE_UNACK",
		"originatorName": "Boiler 7",
		"acknowledged":   false,
		"cleared":        false,
		"assignee":       nil,
		"createdTime":    float64(0),
	}
	got := summarizeLiveAlarms([]map[string]any{alarm}, 1, false)
	checks := []string{
		"There are currently 1 active alarms:",
		"| Type | Severity | Status | Originator | Created |",
		"Overheat",
		"MAJOR",
		"ACTIVE_UNACK",
		"Boiler 7",
		"1970-01-01 00:00:00 UTC",
		"- Alarm 1: Acknowledged: No, Cleared: No, Assignee: None",
		"Want me to acknowledge, clear, or pull more detail on any of these?",
	}
	for _, want := range checks {
		if !strings.Contains(got, want) {
			t.Fatalf("expected summary to contain %q\nfull output:\n%s", want, got)
		}
	}
}

func TestRunAgentLiveAlarmQueryUsesBoundedFirstPage(t *testing.T) {
	mcp := &fakeMCPClient{
		tools: []McpTool{{Name: "getAllAlarms"}},
		responses: []string{`{
			"data": [
				{
					"type": "Overheat",
					"severity": "MAJOR",
					"status": "ACTIVE_UNACK",
					"originatorName": "Boiler 7",
					"acknowledged": false,
					"cleared": false,
					"createdTime": "0"
				}
			],
			"totalElements": 125,
			"hasNext": true
		}`},
	}
	agent := NewAgent(Settings{MaxAlarmPages: 1, MaxObservationChars: 4000}, mcp, nil)
	sessionID := "live-alarm-test"

	got, err := agent.RunAgent(context.Background(), "show me any active alarms right now", nil, nil, &sessionID, nil)
	if err != nil {
		t.Fatalf("RunAgent returned error: %v", err)
	}
	if len(mcp.calls) != 1 {
		t.Fatalf("expected one getAllAlarms call, got %d", len(mcp.calls))
	}
	call := mcp.calls[0]
	if call.name != "getAllAlarms" {
		t.Fatalf("expected getAllAlarms call, got %q", call.name)
	}
	expectedArgs := map[string]any{
		"searchStatus":    "ACTIVE",
		"fetchOriginator": true,
		"sortProperty":    "createdTime",
		"sortOrder":       "DESC",
		"page":            "0",
		"pageSize":        "50",
	}
	for key, want := range expectedArgs {
		if gotArg := call.arguments[key]; gotArg != want {
			t.Fatalf("expected argument %s=%v, got %v", key, want, gotArg)
		}
	}
	checks := []string{
		"There are currently 125 active alarms:",
		"Showing the 1 newest active alarms returned by ThingsBoard.",
		"Overheat",
		"Boiler 7",
		"124 more active alarms were not expanded",
	}
	for _, want := range checks {
		if !strings.Contains(got.Answer, want) {
			t.Fatalf("expected answer to contain %q\nfull answer:\n%s", want, got.Answer)
		}
	}
	if got.Status != "finished" {
		t.Fatalf("expected finished status, got %q", got.Status)
	}
}
