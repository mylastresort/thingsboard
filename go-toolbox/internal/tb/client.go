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
	var out struct{ Token string `json:"token"` }
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
		ID struct{ ID string `json:"id"` } `json:"id"`
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
		ID struct{ ID string `json:"id"` } `json:"id"`
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