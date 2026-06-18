#!/bin/bash

args=$@

echo args $args

entity_token="kvwS3Jp5RRQcmARmgcF1"

# path='./PdM_telemetry_MachineID11_OLD_DATA_random.csv'
path='./PdM_telemetry_MachineID1.csv'
increment_value=40
# if [ $entity_token == "8PyIT47tVem2abB0zi5e" ]; then
# if [ $entity_token == "u0liwrrBwb9dM5fI8uIV" ]; then
#   path='./PdM_telemetry_MachineID1.csv'
# fi

# COUNT=1000

# if [ -n "$1" ]; then
#   if [[ "$1" =~ ^-?[0-9]+$ ]]; then
#     COUNT=$((10#$1))
#   else
#     echo "Parameter is not a valid integer."
#     exit 1
#   fi
# fi

echo -e "DEVICE:\t\tDevice 5"
echo -e "SENSOR:\t\tPressure 3"
echo -e "ACTION:\t\tSending random telemetery data to Thingsboard Cloud {The Pressure Sensor}"
echo -e "LOOP:\t\t$COUNT"
echo -e 'COMMAND:\tmosquitto_pub
                    -d
                    -q 1
                    -h thingsboard
                    -p 1883
                    -t v1/devices/me/telemetry
                    -u "$entity_token"
                    -m "{pressure:$(seq 0.2625 .001 0.7875 | shuf | head -n1)}"
                    > /dev/null'

trap 'echo -e "\Closed at LOOP: $i, PRESSURE: $VALUE"; exit' SIGINT

time=$(cat ./time-between-forecast.txt)

# send just needed data for first forcast
echo ''
while true; do
  # for ((i=1; i<=COUNT; i++))
  # for (( ; ; )); do
  # VALUE=$(seq 0.2625 .001 0.7875 | shuf | head -n1)
  # echo -ne "LOOP: $i, PRESSURE: $VALUE\r"
  paste -d, "$path" | while IFS="," read -r datetime machineId volt rotate pressure vibration; do
    # printf "LOOP: $i, PRESSURE: $pressure, DATETIME: $datetime\r"
    sleep "$time"
    # if [ $entity_token == "8PyIT47tVem2abB0zi5e" ]; then
    #   set_alarm=$(cat ./set-alarm.txt)
    #   echo "set_alarm: $set_alarm"
    #   if [ "$set_alarm" == "1" ]; then
    #     pressure=$(echo "$pressure + $increment_value" | bc)
    #   fi
    # fi
    mosquitto_pub -d -q 1 -h thingsboard -p 1883 -t v1/devices/me/telemetry -u "$entity_token" -m "{rotate:$rotate,pressure:$pressure,volt:$volt,vibration:$vibration}" >/dev/null
  done
  echo "Restarting file read..."
done
