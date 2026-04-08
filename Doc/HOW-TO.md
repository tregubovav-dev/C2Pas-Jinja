
# How-To Guide: Generating Pascal Headers

## 1. Environment Preparation

Before running the extractor, you must have a correctly prepared OpenSSL source tree. 

1.  **Download/Clone**: Use the branch corresponding to your target version (e.g., `openssl-3.6`).
2.  **Configure and Build**: Run `./config` and `make`. 
    *   **Why?** OpenSSL generates several headers dynamically (like `opensslconf.h`). Without these, Clang cannot resolve platform-specific types.

---

## 2. Batch Processing (Recommended)

For processing an entire OpenSSL header tree, use the two batch scripts in the `Examples/` directory. This two-phase approach is the recommended workflow.

### Phase 1: Build the Metadata Database (`ExtractAll.sh`)

Set your OpenSSL root path and run the extraction script from your project directory:

```bash
# Optional: set the OpenSSL root (defaults to $HOME/dev/openssl)
export OPENSSL_ROOT=/path/to/openssl

# Optional: set the output directory for JSON files (defaults to ./db)
export DB_DIR=./db

bash Examples/ExtractAll.sh
```

**Expected output:**
```
====================================================
Extraction summary:
  Processed: 142
  Created:   130
  Skipped:   12   # Headers with no exported symbols — this is normal
  Errors:    0
====================================================
```

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

## 3. Manual Single-File Processing

For per-header extraction and generation, use the Python scripts directly.

### Step 1: Extracting to JSON (`C2Meta.py`)

The `C2Meta.py` script analyzes the C source and produces a language-agnostic API database.

#### Command Example
```bash
python Source/C2Meta.py \
  --header /path/to/openssl/include/openssl/evp.h \
  --search /path/to/openssl/include \
  --num /path/to/openssl/util/libcrypto.num \
  --num /path/to/openssl/util/libssl.num \
  --syms /path/to/openssl/util/other.syms \
  --out evp.json
```

#### Exit Codes
| Code | Meaning |
|------|---------|
| `0` | Success — JSON file written. |
| `254` | No symbols found — JSON file **skipped** (use `--force` to override). |
| Other | Fatal error during extraction. |

#### Options
-   `--force`: Always write the JSON output file, even if no symbols were extracted.

**Note on `.syms`**: OpenSSL uses `other.syms` to define macro-based aliases (e.g., `EVP_MD_name`). Including this file allows the toolchain to treat these macros as proper routines with signatures.

---

### Step 2: Generating the Pascal Unit (`Meta2Pas.py`)

The `Meta2Pas.py` script takes the JSON database and applies a Jinja2 template to create the `.pas` file. The `--template` argument accepts both absolute and relative paths.

#### Command Example
```bash
python Source/Meta2Pas.py \
  --json evp.json \
  --template Examples/TaurusTLSHeader.pas.j2 \
  --type-map Examples/TaurusTLS_type_map.json \
  --escape-symbol _ \
  --out TaurusTLSHeaders_evp.pas
```

---

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
