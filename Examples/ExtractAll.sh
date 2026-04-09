#!/bin/bash

# =============================================================================
# C2Pas-Jinja Batch Extractor
# 
# This script iterates through OpenSSL headers and extracts API metadata into 
# JSON format using C2Meta.py.
# =============================================================================

## Path configurations (Override via environment variables)
# Root of the OpenSSL source tree
[[ -z "$OPENSSL_ROOT" ]] && OPENSSL_ROOT="$HOME/dev/openssl"

# Output directory for JSON files
[[ -z "$DB_DIR" ]] && DB_DIR="./db"

# Location of the Extraction script (relative to this script)
SCRIPT_DIR=$(dirname "$0")
SOURCE_ROOT=$(realpath "$SCRIPT_DIR/../Source")

## Tools
PY="python3"

echo "===================================================="
echo "C2Pas-Jinja: Batch Extraction"
echo "  OpenSSL: $OPENSSL_ROOT"
echo "  Output:  $DB_DIR"
echo "===================================================="

mkdir -p "$DB_DIR"

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
    "$PY" "$SOURCE_ROOT"/C2Meta.py \
        --header "$header" \
        --search "$OPENSSL_ROOT"/include \
        --num "$OPENSSL_ROOT"/util/libcrypto.num \
        --num "$OPENSSL_ROOT"/util/libssl.num \
        --syms "$OPENSSL_ROOT"/util/other.syms \
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
