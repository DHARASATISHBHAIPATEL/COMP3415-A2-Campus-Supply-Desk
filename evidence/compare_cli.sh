#!/bin/sh
# Usage: sh evidence/compare_cli.sh <code-dir>
# Runs a fixed CLI scenario against a fresh save file and prints all output.
dir="$1"; data=$(mktemp -d)/state.json
run() { echo "\$ $*"; (cd "$dir" && python3 -m supplydesk --data "$data" "$@" 2>&1); echo "exit=$?"; }
run catalog
run quote --item notebook:2
run quote --customer student --item bag:2
run quote --customer student --fulfillment delivery --item hoodie:2
run quote --customer student --fulfillment delivery --item hoodie:2 --item notebook:5
run quote --item laptop:1
run quote --item mug:0
run quote --customer student --item pen-pack:7 --item notebook:1
run place --customer student --fulfillment delivery --item hoodie:1 --item mug:2
run place --item bag:3 --item bag:2
run place --item hoodie:9
run orders
run show ORD-0001
run cancel ORD-0001
run cancel ORD-0001
run cancel ORD-0099
run catalog
cat "$data"
