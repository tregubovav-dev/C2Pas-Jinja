#!/bin/bash

# =============================================================================
# C2Pas-Jinja Batch Generator
# 
# This script applies Jinja2 templates to extracted JSON databases to produce
# Delphi (.pas) units.
# =============================================================================

## Path configurations (Override via environment variables)
# Directory containing JSON metadata (produced by ExtractAll.sh)
[[ -z "$DB_DIR" ]] && DB_DIR="./db"

# Output directory for Pascal units
[[ -z "$OUT_DIR" ]] && OUT_DIR="./units"

# Location of scripts and resources (relative to this script)
SCRIPT_DIR=$(dirname "$0")
SOURCE_ROOT=$(realpath "$SCRIPT_DIR/../Source")
MAP_FILE="$SCRIPT_DIR/TaurusTLS_type_map.json"

## Tools
PY="python3"

echo "===================================================="
echo "C2Pas-Jinja: Batch Pascal Generation"
echo "  Input DB: $DB_DIR"
echo "  Output:   $OUT_DIR"
echo "  Map:      $MAP_FILE"
echo "===================================================="

mkdir -p "$OUT_DIR"

COUNT=0
ERRORS=0

# Iterate over all JSON files in the database directory
for db_file in "$DB_DIR"/*.json
do
    # Check if files exist to avoid processing empty globs
    [ -e "$db_file" ] || continue
    
    FN=$(basename "$db_file" .json)
    TPL_FILE="$SCRIPT_DIR/GenericHeader.pas.j2"
    
    # Run the generator
    # We suppress standard output here to keep the batch log clean.
    "$PY" "$SOURCE_ROOT"/Meta2Pas.py \
        --json "$db_file" \
        --template "$TPL_FILE" \
        --type-map "$MAP_FILE" \
        --escape-symbol _ \
        --out "$OUT_DIR/$FN.pas" > /dev/null 2>&1
    
    RET=$?
    
    if [ $RET -eq 0 ]; then
        echo " [+] $FN: Generated Pascal unit"
        ((COUNT++))
    else
        echo " [!] $FN: FAILED (Code $RET)"
        ((ERRORS++))
    fi
done

echo "===================================================="
echo "Generation summary:"
echo "  Successfully Generated: $COUNT"
echo "  Errors:                 $ERRORS"
echo "===================================================="
