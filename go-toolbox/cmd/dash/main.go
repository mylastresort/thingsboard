package main

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"os/exec"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

//go:embed devices.json
var defaultConfig []byte

//go:embed PdM_telemetry_MachineID1.csv
var pdm1CSV []byte

type device struct {
	Name   string  `json:"name"`
	Token  string  `json:"token"`
	Metric string  `json:"metric"`
	Min    float64 `json:"min"`
	Max    float64 `json:"max"`
	SleepS int     `json:"sleep_s"`
}

type config struct {
	MQTTHost string   `json:"mqtt_host"`
	MQTTPort int      `json:"mqtt_port"`
	Devices  []device `json:"devices"`
}

func main() {
	fs := flag.NewFlagSet("dash", flag.ExitOnError)
	configFile := fs.String("config", "", "device config file (default: embedded devices.json)")
	fs.Parse(os.Args[1:])

	raw := defaultConfig
	if *configFile != "" {
		var err error
		raw, err = os.ReadFile(*configFile)
		if err != nil {
			log.Fatalf("open config: %v", err)
		}
	}

	var cfg config
	if err := json.Unmarshal(raw, &cfg); err != nil {
		log.Fatalf("parse config: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() { <-sigs; cancel() }()

	var wg sync.WaitGroup
	for _, d := range cfg.Devices {
		wg.Add(1)
		log.Printf("starting %s (%s)", d.Name, d.Metric)
		if d.Metric == "pdm1" {
			go runPdM1(ctx, &wg, d, cfg.MQTTHost, cfg.MQTTPort)
		} else {
			go runDevice(ctx, &wg, d, cfg.MQTTHost, cfg.MQTTPort)
		}
	}

	log.Printf("dash: %d devices running", len(cfg.Devices))
	wg.Wait()
	log.Printf("dash: stopped")
}

func sleep(ctx context.Context, d time.Duration) bool {
	select {
	case <-time.After(d):
		return true
	case <-ctx.Done():
		return false
	}
}

func mqttPub(ctx context.Context, host string, port int, token, payload string) {
	cmd := exec.CommandContext(ctx, "mosquitto_pub",
		"-q", "1",
		"-h", host, "-p", fmt.Sprint(port),
		"-t", "v1/devices/me/telemetry",
		"-u", token,
		"-m", payload,
	)
	cmd.Run() // ponytail: errors logged by caller if ctx is live
}

func runDevice(ctx context.Context, wg *sync.WaitGroup, d device, host string, port int) {
	defer wg.Done()
	s := time.Duration(d.SleepS) * time.Second
	if s == 0 {
		s = 2 * time.Second
	}
	for {
		value := d.Min + rand.Float64()*(d.Max-d.Min)
		mqttPub(ctx, host, port, d.Token, fmt.Sprintf(`{%s:%.4f}`, d.Metric, value))
		if !sleep(ctx, s) {
			return
		}
	}
}

// runPdM1 replaces telemetry_PdM1.sh: streams CSV rows in a loop via MQTT.
// CSV columns: datetime,machineId,volt,rotate,pressure,vibration
func runPdM1(ctx context.Context, wg *sync.WaitGroup, d device, host string, port int) {
	defer wg.Done()
	s := time.Duration(d.SleepS) * time.Second
	if s == 0 {
		s = 2 * time.Second
	}
	for {
		r := csv.NewReader(bytes.NewReader(pdm1CSV))
		r.Read() // skip header
		for {
			row, err := r.Read()
			if err != nil {
				break // EOF → restart
			}
			if len(row) < 6 {
				continue
			}
			// volt=row[2], rotate=row[3], pressure=row[4], vibration=row[5]
			payload := fmt.Sprintf(`{rotate:%s,pressure:%s,volt:%s,vibration:%s}`,
				row[3], row[4], row[2], row[5])
			mqttPub(ctx, host, port, d.Token, payload)
			if !sleep(ctx, s) {
				return
			}
		}
		if ctx.Err() != nil {
			return
		}
		log.Printf("pdm1: restarting CSV")
	}
}