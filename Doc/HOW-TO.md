
# How-To Guide: Generating Pascal Headers

## 1. Environment Preparation

Before running the extractor, you must have a correctly prepared OpenSSL source tree. 

1.  **Download/Clone**: Use the branch corresponding to your target version (e.g., `openssl-3.6`).
2.  **Configure and Build**: Run `./config` and `make`. 
    *   **Why?** OpenSSL generates several headers dynamically (like `opensslconf.h`). Without these, Clang cannot resolve platform-specific types.

---

## 2. Step 1: Extracting to JSON (`C2Meta.py`)

The `C2Meta.py` script analyzes the C source and produces a language-agnostic API database.

### Command Example
```bash
python Source/C2Meta.py \
  --header /path/to/openssl/include/openssl/evp.h \
  --search /path/to/openssl/include \
  --num /path/to/openssl/util/libcrypto.num \
  --syms /path/to/openssl/util/other.syms \
  --out evp.json
```

**Note on `.syms`**: OpenSSL uses `other.syms` to define macro-based aliases (e.g., `EVP_MD_name`). Including this file allows the toolchain to treat these macros as proper routines with signatures.

---

## 3. Step 2: Generating the Pascal Unit (`Meta2Pas.py`)

The `Meta2Pas.py` script takes the JSON database and applies a Jinja2 template to create the `.pas` file.

### Command Example
```bash
python Source/Meta2Pas.py \
  --json evp.json \
  --template Examples/taurustls.j2 \
  --type-map Examples/delphi_map.json \
  --escape-symbol & \
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

## 5. Troubleshooting
*   **Zero Routines Extracted**: Ensure you are pointing to the **public** header in `include/openssl/` and that you have run `make` in the OpenSSL directory.
*   **Type Mismatch**: Check `delphi_map.json`. Ensure you are using the correct pointer depth (e.g., `"1": "PByte"`) for types that should not use the default `P` prefix.
*   **Jinja2 Errors**: Ensure all custom filters (`pas_sig`, `version_val`) are registered in `Meta2Pas.py`.
