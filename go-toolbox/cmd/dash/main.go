package main

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/csv"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
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
	TBName string  `json:"tb_name"`
	Token  string  `json:"token,omitempty"`
	Metric string  `json:"metric"`
	Min    float64 `json:"min"`
	Max    float64 `json:"max"`
	SleepS int     `json:"sleep_s"`
}

type config struct {
	MQTTHost   string   `json:"mqtt_host"`
	MQTTPort   int      `json:"mqtt_port"`
	TBURL      string   `json:"tb_url"`
	TBUser     string   `json:"tb_user"`
	TBPassword string   `json:"tb_password"`
	Devices    []device `json:"devices"`
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

	tokens, err := resolveTokens(cfg)
	if err != nil {
		log.Fatalf("resolve tokens: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() { <-sigs; cancel() }()

	var wg sync.WaitGroup
	for _, d := range cfg.Devices {
		token := tokens[d.TBName]
		if token == "" {
			log.Printf("WARNING: no token resolved for %q, skipping", d.TBName)
			continue
		}
		d.Token = token
		wg.Add(1)
		log.Printf("starting %s (%s) tb_name=%s", d.Name, d.Metric, d.TBName)
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

type tbPageData struct {
	Data []struct {
		ID struct {
			ID string `json:"id"`
		} `json:"id"`
		Name string `json:"name"`
	} `json:"data"`
	TotalElements int `json:"totalElements"`
}

type tbCredentials struct {
	CredentialsID string `json:"credentialsId"`
}

func resolveTokens(cfg config) (map[string]string, error) {
	if cfg.TBURL == "" {
		return nil, fmt.Errorf("tb_url is required in config")
	}

	client := &http.Client{Timeout: 10 * time.Second}

	loginBody, _ := json.Marshal(map[string]string{
		"username": cfg.TBUser,
		"password": cfg.TBPassword,
	})
	resp, err := client.Post(cfg.TBURL+"/api/auth/login", "application/json", bytes.NewReader(loginBody))
	if err != nil {
		return nil, fmt.Errorf("login: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("login: status %d: %s", resp.StatusCode, body)
	}
	var loginResp struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&loginResp); err != nil {
		return nil, fmt.Errorf("decode login: %w", err)
	}
	jwt := loginResp.Token

	needTokens := make(map[string]bool)
	for _, d := range cfg.Devices {
		if d.TBName != "" {
			needTokens[d.TBName] = true
		}
	}

	tokens := make(map[string]string)
	pageSize := 200
	page := 0
	for {
		url := fmt.Sprintf("%s/api/tenant/devices?pageSize=%d&page=%d", cfg.TBURL, pageSize, page)
		req, _ := http.NewRequest("GET", url, nil)
		req.Header.Set("X-Authorization", "Bearer "+jwt)
		resp, err := client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("list devices page %d: %w", page, err)
		}
		var pageData tbPageData
		if err := json.NewDecoder(resp.Body).Decode(&pageData); err != nil {
			resp.Body.Close()
			return nil, fmt.Errorf("decode devices page %d: %w", page, err)
		}
		resp.Body.Close()

		for _, dev := range pageData.Data {
			if !needTokens[dev.Name] {
				continue
			}
			credURL := fmt.Sprintf("%s/api/device/%s/credentials", cfg.TBURL, dev.ID.ID)
			credReq, _ := http.NewRequest("GET", credURL, nil)
			credReq.Header.Set("X-Authorization", "Bearer "+jwt)
			credResp, err := client.Do(credReq)
			if err != nil {
				log.Printf("WARNING: get credentials for %s: %v", dev.Name, err)
				continue
			}
			var creds tbCredentials
			if err := json.NewDecoder(credResp.Body).Decode(&creds); err != nil {
				credResp.Body.Close()
				log.Printf("WARNING: decode credentials for %s: %v", dev.Name, err)
				continue
			}
			credResp.Body.Close()
			tokens[dev.Name] = creds.CredentialsID
			delete(needTokens, dev.Name)
		}

		if len(needTokens) == 0 || (page+1)*pageSize >= pageData.TotalElements {
			break
		}
		page++
	}

	for name := range needTokens {
		log.Printf("WARNING: device %q not found in ThingsBoard", name)
	}

	log.Printf("resolved %d device tokens from ThingsBoard API", len(tokens))
	return tokens, nil
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
