
# Architecture Overview: C2Pas-Jinja

The toolchain is designed as a **decoupled pipeline**. It separates the complex task of C-language analysis from the creative task of Pascal code generation. This separation allows developers to update OpenSSL versions or change Pascal coding styles independently.

## 1. Environment & OpenSSL Preparation

Before running the toolchain, the OpenSSL source environment must be correctly prepared. Clang requires a "build-ready" state to resolve macros and generated headers.

### OpenSSL Repository Setup
1.  **Clone and Branch**: Ensure you are on the correct branch for the version you intend to translate.
    ```bash
    git clone https://github.com/openssl/openssl.git
    cd openssl
    git checkout openssl-3.6  # Or your target version
    ```
2.  **Configuration & Build**: **This is a mandatory step.** OpenSSL generates critical headers (like `opensslconf.h`) during the configuration process. Without these, the Clang AST parser will fail to resolve platform-specific types.
    ```bash
    ./config
    make  # A full build is recommended to ensure all headers are generated
    ```

### Folder Structure Requirements
The extractor expects the following OpenSSL directory layout:
-   `include/openssl/`: Contains public API headers (e.g., `evp.h`).
-   `util/`: Contains `.num` and `other.syms` files that list exported symbols.

---

---

## 2. Stage 1: The Extractors

The toolchain now provides two specialized extractors for Stage 1.

### 2.1 Generic Extractor (`C2Meta.py`)
The `C2Meta.py` script is a library-agnostic C-to-JSON parser. It extracts *all* exported declarations (functions, macros, typedefs, structs) encountered within the target header.
-   **No OpenSSL dependencies**: It does not require `.num` or `.syms` files.
-   **Perfect for general C libraries**: Ideal for generating headers for any dynamic library without version-tracking metadata.

### 2.2 OpenSSL Specialized Extractor (`Ossl2Meta.py`)
The `Ossl2Meta.py` script is a direct descendant of the original extractor, specialized for the OpenSSL ecosystem.
*   **Export Resolver**: Cross-references every function against OpenSSL's `.num` and `.syms` files.
*   **Historical Version Tracking**: Uses legacy `.num` files (via `--legacy`) to accurately identify when a symbol was first introduced, replacing generic `3_0_0` markers with specific versions (e.g., `1_1_0`).
*   **Safestack Grouping**: Detects `STACK_OF` macro instantiations and groups related helper macros (e.g., `sk_XXX_num`, `ossl_check_XXX_sk_type`) into a specialized `ossl_stacks` collection to prevent global namespace pollution.
*   **Simplified CLI**: Assumes standard OpenSSL directory structures.

### Key Extraction Logic (Shared)
Both extractors utilize the following core `CExtractor` logic:
-   **Clang AST Analysis**: Understands C scoping, macro expansion, and type decay.
-   **Macro Routine Promotion**: Promotes object-like macros that alias routines into the **Routines** list with full signature inheritance.
-   **High-Fidelity Callback Extraction**: 
    -   **Typedef Preservation**: Preserves the original C name for named procedural types.
    -   **Anonymous Promotion**: Promotes "inline" function pointers to named Pascal types using the `{Parent}_{Param}_cb` convention.
    -   **Parameter Intelligence**: Extracts actual parameter names (e.g., `ssl`, `identity`) from the AST instead of using generic `arg1` placeholders.
-   **Signature De-duplication**: Uses a global registry to ensure structurally identical anonymous callbacks share the same type name, while prioritizing existing `typedef` names.
-   **Sugar-Aware Type Parsing**: Preserves "sugared" types (like `EVP_MD_CTX`) for parameters while resolving their underlying definitions for type declarations.

---

---

## 3. Stage 2: The Generator (`Meta2Pas.py`)

The generator consumes the JSON database and applies a Jinja2 template to produce the final `.pas` unit.

### Hierarchical Type Mapping
The generator uses an external `typemap.json` with a multi-tier priority system:
1.  **Exact Match**: If a specific `pointer_depth` is mapped (e.g., `unsigned char` depth 1 -> `PByte`), it is used as-is.
2.  **Inherited Match**: If the specific depth isn't mapped, it inherits the mapping from the closest lower depth.
3.  **Prefixing Rules**: 
    -   If building from a base type (Depth 0): It replaces a leading `T` with `P` and prepends additional `P` prefixes for higher depths.
    -   **Unmapped Types**: If a type isn't in the map, it prepends `T` for the base type (e.g., `asn1_st` -> `Tasn1_st`) and `P` for pointers.
    -   **Reserved Types**: Built-in Delphi types like `Pointer` are protected from `T` prefixing.

### Case-Insensitive Collision Management
Delphi is case-insensitive, while C is case-sensitive. To prevent `E2004: Identifier redeclared` errors:
-   The generator maintains a global registry of all identifiers across types, routines, and constants.
-   If a collision occurs (e.g., `DH_METHOD` vs `dh_method`), the tool marks the second occurrence with a `collision_with` flag.
-   The template uses this flag to render the conflicting C declaration inside a Pascal comment block, preserving the data without breaking the compiler.

### Jinja2 Custom Extensions
-   **Filters**: 
    -   `version_val`: Converts version strings (e.g., `3_0_0`) into integers for numeric comparison.
    -   `pas_sig`: Assembles C parameters and return types into a valid Delphi signature.
    -   `pas_expression`: Case-insensitive translation of C hex (`0x`/`0X` to `$`) and bitwise operators (`<<` to `shl`, etc.).
-   **Tests**: 
    -   `match`: Enables regex-based filtering of identifiers directly within the template.

### Template Path Resolution
The generator uses the template file's own directory as the Jinja2 search root. This means the `--template` argument accepts both **absolute** and **relative** paths transparently, making it suitable for use from batch scripts in any working directory.

### File Output & Unit Synchronization
-   **CRLF Enforcement**: The generator always enforces Windows-style line endings (`\r\n`).
-   **Unit Name Discovery (Experimental)**: The script provides an optional `--auto-unit-rename` flag. This feature ensures that the target filename matches the `unit Name;` declaration produced by the template, which is required for the Delphi compiler.
-   **Template Context**: The generator injects the `out_file` variable into the Jinja2 context, allowing templates to dynamically generate unit names that align with the intended output path.

---

## 4. Data Flow Diagram

```text
[ OpenSSL Headers ]       [ .num / .syms ]
        |                        |
        +----------+-------------+
                   |
        [ Stage 1: C2Meta.py ] <--- (Clang AST)
                   |
        [ Language-Agnostic JSON ]  --- (exit 254: skipped if empty)
                   |
        +----------+-------------+
        |                        |
[ Jinja2 Template ]      [ typemap.json ]
        |                        |
        +----------+-------------+
                   |
        [ Stage 2: Meta2Pas.py ]
                   |
        [ Final Pascal Unit (.pas) ]
```

## 5. Batch Processing Scripts (`Examples/`)

For processing an entire OpenSSL header tree, two helper scripts are provided in the `Examples/` directory. They implement the recommended two-phase workflow.

### `ExtractOsslAll.sh` — Phase 1: Build the OpenSSL Metadata Database
Iterates over headers in `include/openssl/`, runs `Ossl2Meta.py` on each, and populates `db/`. It supports `OPENSSL_LEGACY_DIR` for historical version enrichment.

### `GenerateAll.sh` — Phase 2: Generate Pascal Units
Iterates over JSON files and runs `Meta2Pas.py`. It contains routing logic to select between `TaurusTLSHeader.pas.j2` (for OpenSSL) and `GenericHeader.pas.j2` (for other libraries).

> **Key benefit of the two-phase approach**: The database only needs to be built once (in a Linux/WSL environment with `clang`). Template iteration and code generation can then be performed independently on any machine.

---

## 6. Design Philosophy: "Transparent & Defensive"
The toolchain follows a "Defensive Generation" philosophy. Templates check if a collection is empty before printing section headers (`type`, `var`, `const`). Combined with "Transparent Collision Management," this ensures that the resulting Pascal unit is always syntactically valid, while providing clear comments for any C identifiers that were suppressed due to Delphi's language constraints.
