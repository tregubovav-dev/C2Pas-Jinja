#!/bin/bash

# =============================================================================
# C2Pas-Jinja: TaurusTLS Batch Generation
# =============================================================================

# Directory containing JSON metadata (Phase 1 output)
[[ -z "$DB_DIR" ]] && DB_DIR="./db"

# Output directory for Pascal units
[[ -z "$OUT_DIR" ]] && OUT_DIR="./units"

# Location of the scripts
SCRIPT_DIR=$(dirname "$0")
SOURCE_ROOT=$(realpath "$SCRIPT_DIR/../Source")
TEMPLATE_DIR=$(realpath "$SCRIPT_DIR")

## Tools
PY="python3"

echo "===================================================="
echo "C2Pas-Jinja: TaurusTLS Generation"
echo "  Input DB:  $DB_DIR"
echo "  Output:    $OUT_DIR"
echo "===================================================="

mkdir -p "$OUT_DIR"

COUNT=0
ERRORS=0

# Iterate over all JSON metadata files
for json_file in "$DB_DIR"/*.json
do
    [ -e "$json_file" ] || continue
    
    FN=$(basename "$json_file" .json)
    
    # Define Target Filename with TaurusTLS prefix
    TARGET_NAME="TaurusTLSHeaders_$FN.pas"
    OUT_PATH="$OUT_DIR/$TARGET_NAME"

    # Template Routing Logic
    # The 'case' statement is the most reliable way to handle header-specific exceptions.
    case "$FN" in
        "obj_mac")
            TEMPLATE="$TEMPLATE_DIR/TaurusTLSHeader_obj_mac.pas.j2"
            ;;
        *)
            # Default template for all other headers
            TEMPLATE="$TEMPLATE_DIR/TaurusTLSHeader.pas.j2"
            ;;
    esac

    echo "Generating: $TARGET_NAME using $(basename "$TEMPLATE") ..."

    "$PY" "$SOURCE_ROOT"/Meta2Pas.py \
        --json "$json_file" \
        --template "$TEMPLATE" \
        --type-map "$TEMPLATE_DIR/TaurusTLS_type_map.json" \
        --out "$OUT_PATH" > /dev/null 2>&1

    if [ $? -eq 0 ]; then
        ((COUNT++))
    else
        echo "  ERROR: Failed to generate $TARGET_NAME"
        ((ERRORS++))
    fi
done

echo "===================================================="
echo "Generation summary:"
echo "  Successfully Generated: $COUNT"
echo "  Errors:                 $ERRORS"
echo "===================================================="
