#!/bin/sh

trap 'exit' INT TERM ERR
trap 'echo && kill 0' EXIT

bash "./telemetry_PdM1.sh" >/dev/null 2>&1 &
echo "bash ./telemetry_PdM1.sh"

for i in $(find . -name "device*.sh"); do
  echo "bash $i"
  bash $i >/dev/null 2>&1 &
done

echo
echo -n "Waiting for all processes to finish"
wait
