// pmtool alarm unit: create and clear ThingsBoard alarms against a device,
// with an optional hold loop that keeps re-touching endTs (mirrors the old
// Python polling script's "keep the alarm alive" behavior).
package main

import (
	"flag"
	"fmt"
	"log"
	"os"
	"time"

	"pmtool/internal/tb"
)

const defaultTBURL = "http://localhost:8080"

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(1)
	}
	switch os.Args[1] {
	case "create":
		cmdCreate(os.Args[2:])
	case "clear":
		cmdClear(os.Args[2:])
	case "help", "-h", "--help":
		usage()
	default:
		fmt.Fprintf(os.Stderr, "alarm: unknown subcommand %q\n\n", os.Args[1])
		usage()
		os.Exit(1)
	}
}

func usage() {
	fmt.Println("Usage:")
	fmt.Println("  alarm create -device <id> -type <type> [flags]   create an alarm, print its ID")
	fmt.Println("  alarm clear -id <alarmID> [flags]                clear an existing alarm")
}

func loginFromFlags(tbURL, user, pass string) *tb.Client {
	if user == "" || pass == "" {
		log.Fatal("need -tb-user/-tb-pass (or TB_USERNAME/TB_PASSWORD)")
	}
	client, err := tb.Login(tbURL, user, pass)
	if err != nil {
		log.Fatalf("login: %v", err)
	}
	return client
}

func cmdCreate(args []string) {
	fs := flag.NewFlagSet("create", flag.ExitOnError)
	tbURL := fs.String("tb-url", defaultTBURL, "ThingsBoard base URL")
	tbUser := fs.String("tb-user", os.Getenv("TB_USERNAME"), "tenant admin username")
	tbPass := fs.String("tb-pass", os.Getenv("TB_PASSWORD"), "tenant admin password")
	deviceID := fs.String("device", "", "device ID the alarm is raised against (required)")
	alarmType := fs.String("type", "", "alarm type, e.g. 'temperature threshold' (required)")
	severity := fs.String("severity", "MAJOR", "CRITICAL | MAJOR | MINOR | WARNING | INDETERMINATE")
	hold := fs.Duration("hold", 0, "keep re-touching endTs for this long after creation (0 = don't)")
	fs.Parse(args)

	if *deviceID == "" || *alarmType == "" {
		log.Fatal("need -device and -type")
	}
	client := loginFromFlags(*tbURL, *tbUser, *tbPass)

	now := time.Now().UnixMilli()
	alarm, err := client.CreateAlarm(*deviceID, *alarmType, *severity, now, now)
	if err != nil {
		log.Fatalf("create alarm: %v", err)
	}
	log.Printf("alarm created: id=%s type=%s severity=%s", alarm.ID.ID, alarm.Type, alarm.Severity)

	if *hold <= 0 {
		return
	}
	deadline := time.Now().Add(*hold)
	for time.Now().Before(deadline) {
		time.Sleep(time.Second)
		alarm, err = client.UpdateAlarm(alarm, time.Now().UnixMilli())
		if err != nil {
			log.Fatalf("update alarm: %v", err)
		}
	}
	log.Printf("hold complete: id=%s", alarm.ID.ID)
}

func cmdClear(args []string) {
	fs := flag.NewFlagSet("clear", flag.ExitOnError)
	tbURL := fs.String("tb-url", defaultTBURL, "ThingsBoard base URL")
	tbUser := fs.String("tb-user", os.Getenv("TB_USERNAME"), "tenant admin username")
	tbPass := fs.String("tb-pass", os.Getenv("TB_PASSWORD"), "tenant admin password")
	alarmID := fs.String("id", "", "alarm ID to clear (required)")
	fs.Parse(args)

	if *alarmID == "" {
		log.Fatal("need -id")
	}
	client := loginFromFlags(*tbURL, *tbUser, *tbPass)

	if err := client.ClearAlarm(*alarmID); err != nil {
		log.Fatalf("clear alarm: %v", err)
	}
	log.Printf("alarm cleared: id=%s", *alarmID)
}