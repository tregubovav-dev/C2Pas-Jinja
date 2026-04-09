
# How-To Guide: Generating Pascal Headers

## 1. Environment Preparation

Before running the extractor, you must have a correctly prepared OpenSSL source tree. 

1.  **Download/Clone**: Use the branch corresponding to your target version (e.g., `openssl-3.6`).
2.  **Configure and Build**: Run `./config` and `make`. 
    *   **Why?** OpenSSL generates several headers dynamically (like `opensslconf.h`). Without these, Clang cannot resolve platform-specific types.

---

## 2. Batch Processing (Recommended)

For processing an entire OpenSSL header tree, use the two batch scripts in the `Examples/` directory. This two-phase approach is the recommended workflow.

### Phase 1: Build the OpenSSL Metadata Database (`ExtractOsslAll.sh`)

Set your OpenSSL root path and the legacy symbol directory, then run the extraction script:

```bash
# Set the OpenSSL 3.x root
export OPENSSL_ROOT=/home/sasha/dev/openssl

# Optional: Set directory with legacy 1.1.1 .num files
export OPENSSL_LEGACY_DIR=./tmp/nums.1_1_1

bash Examples/ExtractOsslAll.sh
```

**Note for Windows Users**: It is highly recommended to run extraction scripts inside WSL (e.g., Ubuntu-24.04) for native Clang performance and path resolution.

### Phase 2: Generate Pascal Units (`GenerateAll.sh`)

Once the metadata database is built, generate Pascal units from any machine (no `clang` required):

```bash
# Optional overrides (defaults to ./db, ./units)
export DB_DIR=./db
export OUT_DIR=./units

bash Examples/GenerateAll.sh
```

**Expected output:**
```
====================================================
Generation summary:
  Successfully Generated: 130
  Errors:                 0
====================================================
```

> **Tip:** Template selection is automatic. Headers like `obj_mac` are routed to their specialized template (`TaurusTLSHeader_obj_mac.j2`); all others use the default template.

---

### Option A: OpenSSL Specialization (`Ossl2Meta.py`)

The `Ossl2Meta.py` script is optimized for OpenSSL with automatic path resolution and version tracking.

#### Command Example
```bash
python3 Source/Ossl2Meta.py \
  --root /home/sasha/dev/openssl \
  --header ssl.h \
  --legacy ./tmp/nums.1_1_1 \
  --out ssl.json
```

---

### Option B: Generic Extraction (`C2Meta.py`)

Use `C2Meta.py` for standard C libraries that don't use OpenSSL's symbol export lists.

#### Command Example
```bash
python3 Source/C2Meta.py \
  --header /usr/include/sqlite3.h \
  --search /usr/include \
  --out sqlite.json
```

---

### Step 2: Generating the Pascal Unit (`Meta2Pas.py`)

The `Meta2Pas.py` script takes the JSON database and applies a Jinja2 template to create the `.pas` file. The `--template` argument accepts both absolute and relative paths.

#### Options
-   `--auto-unit-rename`: (Optional) Scans the rendered output for `unit XXXX;`. If found, it automatically renames the final output file to `XXXX.pas`. Use this to ensure your filename matches your Delphi unit declaration.
-   `--escape-symbol`: Choose between `_` (default) or `&` for reserved word escaping.

#### Template Context Variables
Inside your Jinja2 templates, the following additional variables are available:
-   `out_file`: The basename of the output file defined in the `--out` parameter (e.g., `ssl.pas`).
-   `routines`, `static_routines`, `constants`, `types`, `enums`, `callbacks`: The API metadata collections.

---

## 4. Advanced Batch Conversion: TaurusTLS

For specialized project naming conventions, use the dedicated TaurusTLS generation script:

```bash
# Set input and output directories
export DB_DIR=./db
export OUT_DIR=./units

# Generates files with 'TaurusTLSHeaders_' prefix
bash Examples/GenerateTaurusTlsAll.sh
```

## 4. Template Usage Examples

### Example A: Basic Template (Opaque Types)
```jinja2
{% if types %}
type
  {% for t in types %}
  P{{ t.name }} = Pointer;
  {$EXTERNALSYM P{{ t.name }}}
  {% endfor %}
{% endif %}
```

### Example B: Advanced Template (TaurusTLS Architecture)
The toolchain automatically promotes anonymous C function pointers. Declare these before the routines that use them:

```jinja2
{% if callbacks %}
type
{% for c in callbacks %}
  {{ c.name }} = {{ c | pas_sig(is_var=True) }};
{% endfor %}
{% endif %}
```

### Example C: Identifier Escaping
By using the `pas_name` filter, reserved words are automatically escaped based on your `--escape-symbol` choice:
```jinja2
{% for p in r.params %}
  {{ p.name | pas_name }}: {{ p.type | pas_type }};
{% endfor %}
```
*Default value for `--escape-symbol` is `_`, a C parameter named `type` becomes `_type` in Pascal.*
*If `--escape-symbol &` is used, a C parameter named `type` becomes `&type` in Pascal.*

---

## 5. CI/CD Integration

The `C2Meta.py` exit code `254` is designed for use in shell scripts to gracefully skip headers with no exported symbols:

```bash
python3 Source/C2Meta.py ... --out api.json
EXIT=$?
if [ $EXIT -eq 254 ]; then
  echo "No symbols found — skipping generation step."
elif [ $EXIT -ne 0 ]; then
  echo "Extraction failed with code $EXIT"
  exit $EXIT
fi
```

---

## 6. Troubleshooting
*   **Zero Routines Extracted**: Ensure you are pointing to the **public** header in `include/openssl/` and that you have run `make` in the OpenSSL directory.
*   **JSON file not created**: If no symbols are exported, `C2Meta.py` skips file creation (exit `254`). This is by design. Use `--force` to override.
*   **Type Mismatch**: Check `TaurusTLS_type_map.json`. Ensure you are using the correct pointer depth (e.g., `"1": "PByte"`) for types that should not use the default `P` prefix.
*   **Jinja2 Errors**: Ensure all custom filters (`pas_sig`, `version_val`) are registered in `Meta2Pas.py`.
*   **`TemplateNotFound` Error**: The `--template` path must point to an existing `.j2` file. Both absolute and relative paths are supported.
