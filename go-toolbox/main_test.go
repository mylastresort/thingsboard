package main

import (
	"os"
	"testing"
)

func TestParseMachineFilterEmptyUsesMax(t *testing.T) {
	allowed, useMax := parseMachineFilter("")
	if !useMax || allowed != nil {
		t.Fatalf("want useMax=true, allowed=nil; got useMax=%v allowed=%v", useMax, allowed)
	}
}

func TestParseMachineFilterExplicitList(t *testing.T) {
	allowed, useMax := parseMachineFilter(" 1, 2,3 ")
	if useMax {
		t.Fatal("want useMax=false for explicit list")
	}
	for _, id := range []int{1, 2, 3} {
		if !allowed[id] {
			t.Fatalf("expected machine %d in allowed set %v", id, allowed)
		}
	}
	if allowed[4] {
		t.Fatal("machine 4 should not be allowed")
	}
}

func TestShouldLoadMaxMachines(t *testing.T) {
	if !shouldLoad(5, 2, nil, true, 3) {
		t.Fatal("loadedCount 2 < max 3 should load")
	}
	if shouldLoad(5, 3, nil, true, 3) {
		t.Fatal("loadedCount 3 >= max 3 should not load")
	}
}

func TestShouldLoadExplicitList(t *testing.T) {
	allowed := map[int]bool{7: true}
	if !shouldLoad(7, 0, allowed, false, 100) {
		t.Fatal("machine 7 is in the allow-list, should load")
	}
	if shouldLoad(8, 0, allowed, false, 100) {
		t.Fatal("machine 8 is not in the allow-list, should not load")
	}
}

func TestParseTsRoundTrip(t *testing.T) {
	ts, err := parseTs("2023-06-01 12:00:00")
	if err != nil {
		t.Fatalf("parseTs error: %v", err)
	}
	if ts <= 0 {
		t.Fatalf("expected positive epoch millis, got %d", ts)
	}
	if _, err := parseTs("not-a-date"); err == nil {
		t.Fatal("expected error for malformed date")
	}
}

func TestLoadKeyedEventsSkipsUnknownMachines(t *testing.T) {
	dir := t.TempDir()
	writeCSV(t, dir+"/PdM_errors.csv", "datetime,machineID,errorID\n2023-01-01 00:00:00,1,error1\n2023-01-01 00:00:00,99,error2\n")

	machineToDevice := map[int]string{1: "dev-1"}
	var got []tsPoint
	track := func(deviceID string, ts int64, kv map[string]string) {
		got = append(got, tsPoint{Ts: ts, Values: kv})
	}

	if err := loadKeyedEvents(dir, "PdM_errors.csv", "error_", machineToDevice, track); err != nil {
		t.Fatalf("loadKeyedEvents: %v", err)
	}
	if len(got) != 1 {
		t.Fatalf("expected 1 point (machine 99 has no device), got %d: %v", len(got), got)
	}
	if got[0].Values["error_error1"] != "1" {
		t.Fatalf("unexpected values: %v", got[0].Values)
	}
}

func writeCSV(t *testing.T, path, content string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatalf("writeCSV: %v", err)
	}
}