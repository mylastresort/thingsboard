package tb

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type TsPoint struct {
	Ts     int64             `json:"ts"`
	Values map[string]string `json:"values"`
}

// Alarm mirrors the subset of ThingsBoard's alarm JSON this tool touches.
// ponytail: only the fields the create/update/clear flow needs, not a full
// schema mirror — add fields if a later unit needs them.
type Alarm struct {
	ID *struct {
		ID string `json:"id"`
	} `json:"id,omitempty"`
	Type       string `json:"type"`
	Originator struct {
		ID         string `json:"id"`
		EntityType string `json:"entityType"`
	} `json:"originator"`
	Severity string `json:"severity"`
	StartTs  int64  `json:"startTs"`
	EndTs    int64  `json:"endTs"`
}

type Client struct {
	BaseURL string
	token   string
	http    *http.Client
}

func Login(baseURL, user, pass string) (*Client, error) {
	body, _ := json.Marshal(map[string]string{"username": user, "password": pass})
	resp, err := http.Post(baseURL+"/api/auth/login", "application/json", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("login failed (%d): %s", resp.StatusCode, b)
	}
	var out struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return nil, err
	}
	return &Client{BaseURL: baseURL, token: out.Token, http: &http.Client{Timeout: 30 * time.Second}}, nil
}

func (c *Client) do(method, path string, body any) (*http.Response, error) {
	var r io.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		r = bytes.NewReader(b)
	}
	req, err := http.NewRequest(method, c.BaseURL+path, r)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Authorization", "Bearer "+c.token)
	return c.http.Do(req)
}

func (c *Client) FindDeviceByName(name string) (id string, found bool, err error) {
	resp, err := c.do(http.MethodGet, "/api/tenant/devices?deviceName="+name, nil)
	if err != nil {
		return "", false, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return "", false, nil
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", false, fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	var out struct {
		ID struct {
			ID string `json:"id"`
		} `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", false, err
	}
	return out.ID.ID, true, nil
}

func (c *Client) CreateDevice(name, deviceType, label string) (string, error) {
	resp, err := c.do(http.MethodPost, "/api/device", map[string]string{
		"name": name, "type": deviceType, "label": label,
	})
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	var out struct {
		ID struct {
			ID string `json:"id"`
		} `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return "", err
	}
	return out.ID.ID, nil
}

func (c *Client) SaveAttributes(deviceID string, attrs map[string]any) error {
	resp, err := c.do(http.MethodPost, "/api/plugins/telemetry/DEVICE/"+deviceID+"/attributes/SERVER_SCOPE", attrs)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	return nil
}

func (c *Client) SaveTimeseries(deviceID string, points []TsPoint) error {
	resp, err := c.do(http.MethodPost, "/api/plugins/telemetry/DEVICE/"+deviceID+"/timeseries/ANY", points)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	return nil
}

// CreateAlarm POSTs a new alarm and returns it (with ID populated) — same
// endpoint TB uses for both create and update, distinguished only by
// whether the body carries an id.
func (c *Client) CreateAlarm(deviceID, alarmType, severity string, startTs, endTs int64) (Alarm, error) {
	a := Alarm{Type: alarmType, Severity: severity, StartTs: startTs, EndTs: endTs}
	a.Originator.ID = deviceID
	a.Originator.EntityType = "DEVICE"
	return c.postAlarm(a)
}

// UpdateAlarm re-POSTs an existing alarm with a new endTs (the Python
// script's "keep the alarm alive" poll loop).
func (c *Client) UpdateAlarm(a Alarm, endTs int64) (Alarm, error) {
	a.EndTs = endTs
	return c.postAlarm(a)
}

func (c *Client) postAlarm(a Alarm) (Alarm, error) {
	resp, err := c.do(http.MethodPost, "/api/alarm", a)
	if err != nil {
		return Alarm{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return Alarm{}, fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	var out Alarm
	if err := json.NewDecoder(resp.Body).Decode(&out); err != nil {
		return Alarm{}, err
	}
	return out, nil
}

// ClearAlarm clears an alarm by ID.
func (c *Client) ClearAlarm(alarmID string) error {
	resp, err := c.do(http.MethodPost, "/api/alarm/"+alarmID+"/clear", nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("status %d: %s", resp.StatusCode, b)
	}
	return nil
}