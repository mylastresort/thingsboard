#!/bin/sh
# scripts/run-agent-evals.sh
set -e
for dir in tests/*/; do
  files=$(find "$dir" -name "*.test.json")
  [ -z "$files" ] && continue
  cfg="${dir}test_config.json"
  if [ -f "$cfg" ]; then
    adk eval thingsboard_ops_agent $files --config_file_path="$cfg" --print_detailed_results
  else
    adk eval thingsboard_ops_agent $files --print_detailed_results
  fi
done