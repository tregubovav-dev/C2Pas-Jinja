# How-To Guide: Generating Pascal Headers

## 1. Environment Preparation

Before running the extractor, you must have a correctly prepared OpenSSL source tree. 

1.  **Clone and Checkout**: Use the branch corresponding to your target version (e.g., `openssl-3.6`).
2.  **Configure and Build**: Run `./config` and `make`. 
    *   **Why?** OpenSSL generates several headers dynamically (like `opensslconf.h`). If these are missing, Clang will not be able to resolve platform-specific types, leading to incomplete JSON metadata.

---

## 2. Step 1: Extracting to JSON

The `ast2json.py` script analyzes the C source and produces a language-agnostic API database.

### Command Example
```bash
python Source/ast2json.py \
  --header /path/to/openssl/include/openssl/evp.h \
  --search /path/to/openssl/include \
  --num /path/to/openssl/util/libcrypto.num \
  --syms /path/to/openssl/util/other.syms \
  --out evp.json
```

### Important Notes on Paths:
*   **The Header**: Always point to the **public** header in `include/openssl/`. Internal headers in `crypto/` often lack the function declarations listed in the export files.
*   **The `.num` files**: These are the "Source of Truth" for exported functions. The script uses these to filter out private internal functions.
*   **The `.syms` files**: OpenSSL uses `other.syms` to define macro-based aliases (e.g., `EVP_MD_name`). Including this file allows the toolchain to treat these macros as proper routines with signatures.

---

## 3. Step 2: Generating the Pascal Unit

The `json2pas.py` script takes the JSON database and applies a Jinja2 template to create the `.pas` file.

### Command Example
```bash
python Source/json2pas.py \
  --json evp.json \
  --template Examples/taurustls_advanced.j2 \
  --type-map Examples/delphi_map.json \
  --out TaurusTLSHeaders_evp.pas
```

---

## 4. Template Usage Examples

### Example A: Basic Template (Opaque Types & Constants)
This snippet demonstrates how to generate simple opaque pointers and filter out specific constants using regex.

```jinja2
{# --- FILTER TYPES --- #}
{% set filtered_types = types | list %}
{% if filtered_types %}
type
  {% for t in filtered_types %}
  P{{ t.name }} = Pointer;
  {$EXTERNALSYM P{{ t.name }}}
  {% endfor %}
{% endif %}

{# --- FILTER CONSTANTS (Exclude OBJ_ prefix) --- #}
{% set filtered_consts = constants | rejectattr("name", "match", "^OBJ_") | list %}
{% if filtered_consts %}
const
  {% for c in filtered_consts %}
  {{ c.name | pas_name }} = {{ c.value | pas_expression }};
  {% endfor %}
{% endif %}
```

### Example B: Advanced Template (TaurusTLS Architecture)
This example shows the full power of the toolchain, including **Dynamic/Static linking**, **Version Checks**, and **Anonymous Callback Promotion**.

#### 1. Callback & Type Declarations
The toolchain automatically promotes anonymous C function pointers. You must declare these before the routines that use them.

```jinja2
{% if callbacks %}
type
{% for c in callbacks %}
  {{ c.name }} = {{ c | pas_sig(is_var=True) }};
{% endfor %}
{% endif %}
```

#### 2. Dynamic vs. Static Linking
Use conditional compilation to support both `external` imports and functional variables.

```jinja2
{$IFNDEF OPENSSL_STATIC_LINK_MODEL}
var
  {% for r in routines if not r.is_macro and not r.is_inline %}
    {%- if not r.deprecated or r.deprecated | version_val > "1_1_0" | version_val %}
  {{ r.name }}: {{ r | pas_sig(is_var=True) }} = nil;
    {% endif %}
  {% endfor %}
{$ENDIF}
```

#### 3. Version-Aware Loader
The `version_val` filter allows you to implement complex loading logic based on when a function was introduced or removed in OpenSSL.

```jinja2
procedure Load(const ADllHandle: TIdLibHandle; LibVersion: TIdC_UINT; const AFailed: TStringList);
begin
{% for r in routines if not r.is_macro and not r.is_inline %}
  {{ r.name }} := LoadLibFunction(ADllHandle, '{{ r.name }}');
  if not assigned({{ r.name }}) then
  begin
    {{ r.name }} := ERR_{{ r.name }}; // Assign Error Stub
    
    {# Check if function was missing because it's too new for the current DLL #}
    {% if r.introduced %}
    if LibVersion < {{ r.introduced | pas_version }} then
       FuncLoadError := false; 
    {% endif %}
  end;
{% endfor %}
end;
```

#### 4. Inline Routine Wrappers
For C macros and inline functions, the template generates a Pascal body where you can manually implement the logic while keeping the original C declaration as a reference.

```jinja2
{% for r in static_routines %}
{{ r | pas_sig }}
begin
  { Original C Declaration: {{ r.c_decl }} }
  // Manual implementation required
end;
{% endfor %}
```

---

## 5. Troubleshooting
*   **Zero Routines Extracted**: Ensure you are pointing to the `include/openssl/` headers and that you have run `make` in the OpenSSL directory.
*   **Type Mismatch**: Check `delphi_map.json`. Ensure you are using the correct pointer depth (e.g., `"1": "PByte"`) for types that should not use the default `P` prefix logic.
*   **Jinja2 Errors**: If you get a `version_val` not found error, ensure you are using the latest version of `json2pas.py` where the filter is registered.
