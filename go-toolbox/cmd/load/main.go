package main

import (
	"encoding/csv"
	"flag"
	"fmt"
	"log"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"pmtool/internal/tb"
)

const (
	defaultTBURL       = "http://localhost:8080"
	defaultDataPath    = "/data"
	defaultMaxMachines = 100
	defaultWorkers     = 8
	defaultBatchSize   = 1000
	dayMillis          = int64(24 * time.Hour / time.Millisecond)
	csvDateLayout      = "2006-01-02 15:04:05"
)

func main() {
	fs := flag.NewFlagSet("load", flag.ExitOnError)
	tbURL := fs.String("tb-url", defaultTBURL, "ThingsBoard base URL")
	tbUser := fs.String("tb-user", os.Getenv("TB_USERNAME"), "tenant admin username")
	tbPass := fs.String("tb-pass", os.Getenv("TB_PASSWORD"), "tenant admin password")
	dataPath := fs.String("data", defaultDataPath, "directory containing PdM_*.csv files")
	machineIDsFlag := fs.String("machine-ids", "", "comma-separated machine IDs (default: first -max-machines)")
	maxMachines := fs.Int("max-machines", defaultMaxMachines, "cap on machines loaded")
	shiftToNow := fs.Bool("shift-to-now", false, "shift timestamps so latest point lands at now")
	workers := fs.Int("workers", defaultWorkers, "concurrent device pushes")
	dryRun := fs.Bool("dry-run", false, "parse CSVs and print summary; skip ThingsBoard calls")
	fs.Parse(os.Args[1:])

	if !*dryRun && (*tbUser == "" || *tbPass == "") {
		log.Fatal("need -tb-user/-tb-pass (or TB_USERNAME/TB_PASSWORD), or pass -dry-run")
	}

	allowed, useMax := parseMachineFilter(*machineIDsFlag)

	var client *tb.Client
	if !*dryRun {
		var err error
		client, err = tb.Login(*tbURL, *tbUser, *tbPass)
		if err != nil {
			log.Fatalf("login: %v", err)
		}
	}

	machineToDevice, loaded, err := loadMachines(*dataPath, client, allowed, useMax, *maxMachines)
	if err != nil {
		log.Fatalf("loading machines: %v", err)
	}
	log.Printf("machines: %d devices ready", len(machineToDevice))

	deviceTelemetry := map[string][]tb.TsPoint{}
	machineMaxTs := map[int]int64{}

	track := func(machineID int, deviceID string, ts int64, kv map[string]string) {
		if ts > machineMaxTs[machineID] {
			machineMaxTs[machineID] = ts
		}
		deviceTelemetry[deviceID] = append(deviceTelemetry[deviceID], tb.TsPoint{Ts: ts, Values: kv})
	}

	for _, spec := range []struct{ file, prefix string }{
		{"PdM_telemetry.csv", ""},
		{"PdM_errors.csv", "error_"},
		{"PdM_failures.csv", "failure_"},
		{"PdM_maint.csv", "maintenance_"},
	} {
		if spec.prefix == "" {
			if err := loadTelemetry(*dataPath, machineToDevice, track); err != nil {
				log.Fatalf("loading telemetry: %v", err)
			}
		} else {
			if err := loadKeyedEvents(*dataPath, spec.file, spec.prefix, machineToDevice, track); err != nil {
				log.Fatalf("loading %s: %v", spec.file, err)
			}
		}
	}

	totalPoints := 0
	for _, pts := range deviceTelemetry {
		totalPoints += len(pts)
	}

	if *shiftToNow {
		shifted := shiftMachineTelemetryToNow(machineToDevice, machineMaxTs, deviceTelemetry, time.Now().UnixMilli())
		log.Printf("shift-to-now: %d machines rounded to whole-day offsets", shifted)
	}

	log.Printf("telemetry: %d points across %d devices", totalPoints, len(deviceTelemetry))

	if *dryRun {
		log.Printf("dry-run: skipping push (%d machines simulated)", loaded)
		return
	}

	pushAll(client, deviceTelemetry, *workers)
	log.Printf("done")
}

func parseMachineFilter(csvIDs string) (allowed map[int]bool, useMax bool) {
	if strings.TrimSpace(csvIDs) == "" {
		return nil, true
	}
	allowed = map[int]bool{}
	for _, s := range strings.Split(csvIDs, ",") {
		id, err := strconv.Atoi(strings.TrimSpace(s))
		if err != nil {
			log.Fatalf("invalid -machine-ids entry %q: %v", s, err)
		}
		allowed[id] = true
	}
	return allowed, false
}

func shouldLoad(machineID, loadedCount int, allowed map[int]bool, useMax bool, max int) bool {
	if useMax {
		return loadedCount < max
	}
	return allowed[machineID]
}

func readCSVRows(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	rows, err := csv.NewReader(f).ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, fmt.Errorf("%s: empty", path)
	}
	return rows, nil
}

func parseTs(s string) (int64, error) {
	t, err := time.Parse(csvDateLayout, s)
	if err != nil {
		return 0, err
	}
	return t.UnixMilli(), nil
}

func loadMachines(dataPath string, client *tb.Client, allowed map[int]bool, useMax bool, max int) (map[int]string, int, error) {
	rows, err := readCSVRows(dataPath + "/PdM_machines.csv")
	if err != nil {
		return nil, 0, err
	}
	machineToDevice := map[int]string{}
	loaded := 0
	for _, row := range rows[1:] {
		machineID, err := strconv.Atoi(row[0])
		if err != nil || !shouldLoad(machineID, loaded, allowed, useMax, max) {
			continue
		}
		name := fmt.Sprintf("PdM-Machine-%d", machineID)
		var deviceID string
		if client == nil {
			deviceID = fmt.Sprintf("dryrun-%d", machineID)
		} else {
			existing, found, err := client.FindDeviceByName(name)
			if err != nil {
				return nil, 0, fmt.Errorf("lookup %s: %w", name, err)
			}
			if found {
				deviceID = existing
			} else {
				deviceID, err = client.CreateDevice(name, "PdM-"+row[1], fmt.Sprintf("Predictive Maintenance Machine %d", machineID))
				if err != nil {
					return nil, 0, fmt.Errorf("create %s: %w", name, err)
				}
				if err := client.SaveAttributes(deviceID, map[string]any{
					"model": row[1], "age": row[2], "machineId": machineID,
				}); err != nil {
					log.Printf("warn: attributes for %s: %v", name, err)
				}
			}
		}
		machineToDevice[machineID] = deviceID
		loaded++
	}
	return machineToDevice, loaded, nil
}

type tsTrackFunc func(machineID int, deviceID string, ts int64, kv map[string]string)

func loadTelemetry(dataPath string, machineToDevice map[int]string, track tsTrackFunc) error {
	rows, err := readCSVRows(dataPath + "/PdM_telemetry.csv")
	if err != nil {
		return err
	}
	header := rows[0]
	skipped := 0
	for i, row := range rows[1:] {
		ts, err := parseTs(row[0])
		machineID, idErr := strconv.Atoi(row[1])
		if err != nil || idErr != nil {
			log.Printf("skip telemetry row %d", i+2)
			skipped++
			continue
		}
		deviceID, ok := machineToDevice[machineID]
		if !ok {
			skipped++
			continue
		}
		kv := map[string]string{}
		for j := 2; j < len(row) && j < len(header); j++ {
			kv[header[j]] = row[j]
		}
		track(machineID, deviceID, ts, kv)
	}
	log.Printf("telemetry: %d loaded, %d skipped", len(rows)-1-skipped, skipped)
	return nil
}

func loadKeyedEvents(dataPath, file, keyPrefix string, machineToDevice map[int]string, track tsTrackFunc) error {
	rows, err := readCSVRows(dataPath + "/" + file)
	if err != nil {
		return err
	}
	skipped := 0
	for i, row := range rows[1:] {
		ts, err := parseTs(row[0])
		machineID, idErr := strconv.Atoi(row[1])
		if err != nil || idErr != nil {
			log.Printf("skip %s row %d", file, i+2)
			skipped++
			continue
		}
		deviceID, ok := machineToDevice[machineID]
		if !ok {
			skipped++
			continue
		}
		track(machineID, deviceID, ts, map[string]string{keyPrefix + row[2]: "1"})
	}
	log.Printf("%s: %d loaded, %d skipped", file, len(rows)-1-skipped, skipped)
	return nil
}

func shiftMachineTelemetryToNow(machineToDevice map[int]string, machineMaxTs map[int]int64, deviceTelemetry map[string][]tb.TsPoint, currentTimeMs int64) int {
	shifted := 0
	for machineID, deviceID := range machineToDevice {
		maxTs := machineMaxTs[machineID]
		if maxTs == 0 {
			continue
		}
		timeDiff := currentTimeMs - maxTs
		timeDiff -= timeDiff % dayMillis
		points := deviceTelemetry[deviceID]
		for i := range points {
			points[i].Ts += timeDiff
		}
		shifted++
	}
	return shifted
}

func pushAll(client *tb.Client, deviceTelemetry map[string][]tb.TsPoint, workers int) {
	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	var mu sync.Mutex
	failed := 0
	for deviceID, points := range deviceTelemetry {
		wg.Add(1)
		sem <- struct{}{}
		go func(deviceID string, points []tb.TsPoint) {
			defer wg.Done()
			defer func() { <-sem }()
			for start := 0; start < len(points); start += defaultBatchSize {
				end := min(start+defaultBatchSize, len(points))
				if err := client.SaveTimeseries(deviceID, points[start:end]); err != nil {
					log.Printf("push %s [%d:%d]: %v", deviceID, start, end, err)
					mu.Lock()
					failed++
					mu.Unlock()
					return
				}
			}
		}(deviceID, points)
	}
	wg.Wait()
	if failed > 0 {
		log.Printf("warn: %d devices failed", failed)
	}
}
