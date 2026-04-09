#!/bin/bash

# =============================================================================
# C2Pas-Jinja Batch Extractor
# 
# This script iterates through OpenSSL headers and extracts API metadata into 
# JSON format using Ossl2Meta.py.
# =============================================================================

## Path configurations (Override via environment variables)
# Root of the OpenSSL source tree
[[ -z "$OPENSSL_ROOT" ]] && OPENSSL_ROOT="$HOME/dev/openssl"

# (Optional) Directory containing legacy .num files (e.g. from OpenSSL 1.1.1)
# Used for accurate "introduced" version tracking.
[[ -z "$OPENSSL_LEGACY_DIR" ]] && OPENSSL_LEGACY_DIR=""

# Output directory for JSON files
[[ -z "$DB_DIR" ]] && DB_DIR="./db"

# Location of the Extraction script (relative to this script)
SCRIPT_DIR=$(dirname "$0")
SOURCE_ROOT=$(realpath "$SCRIPT_DIR/../Source")

## Tools
PY="python3"

echo "===================================================="
echo "C2Pas-Jinja: Batch Extraction"
echo "  OpenSSL:        $OPENSSL_ROOT"
if [[ -n "$OPENSSL_LEGACY_DIR" ]]; then
echo "  Legacy Symbols: $OPENSSL_LEGACY_DIR"
fi
echo "  Output:         $DB_DIR"
echo "===================================================="

mkdir -p "$DB_DIR"

# Prepare legacy flags if directory is provided
LEGACY_FLAGS=""
if [[ -n "$OPENSSL_LEGACY_DIR" ]]; then
    LEGACY_FLAGS="--legacy $OPENSSL_LEGACY_DIR"
fi

COUNT=0
SKIPPED=0
ERRORS=0

# Iterate over public OpenSSL headers
for header in "$OPENSSL_ROOT"/include/openssl/*.h
do
    FN=$(basename "$header" .h)
    
    # Skip internal headers (prefixed with _)
    if [[ "$FN" == _* ]]; then
        continue
    fi

    # Run the extractor
    # We suppress standard output here to keep the batch log clean, 
    # but handle the exit codes specifically.
    "$PY" "$SOURCE_ROOT"/Ossl2Meta.py \
        --root "$OPENSSL_ROOT" \
        --header "$FN.h" \
        $LEGACY_FLAGS \
        --out "$DB_DIR/$FN.json" > /dev/null 2>&1
    
    RET=$?
    
    if [ $RET -eq 0 ]; then
        echo " [+] $FN: Generated"
        ((COUNT++))
    elif [ $RET -eq 254 ]; then
        echo " [-] $FN: Skipped (No symbols exported)"
        ((SKIPPED++))
    else
        echo " [!] $FN: FAILED (Code $RET)"
        ((ERRORS++))
    fi
done

echo "===================================================="
echo "Extraction summary:"
echo "  Processed: $((COUNT + SKIPPED + ERRORS))"
echo "  Created:   $COUNT"
echo "  Skipped:   $SKIPPED"
echo "  Errors:    $ERRORS"
echo "===================================================="
