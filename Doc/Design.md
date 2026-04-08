
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

## 2. Stage 1: The Extractor (`C2Meta.py`)

The extractor's job is to turn a C header into a language-agnostic "API Database" in JSON format.

### Clang AST Analysis
The tool uses `libclang` to parse the header. Unlike regex-based tools, this understands C scoping, macro expansion, and type decay. It uses `os.path.realpath` for all path comparisons to ensure reliability across different environments.

### Key Logic Modules
-   **Export Resolver**: Cross-references every function found in the AST against OpenSSL's `.num` and `.syms` files. If a function isn't exported, it is ignored.
-   **Macro Routine Promotion**: If a `#define aa bb` exists where `bb` is a known routine, the tool promotes `aa` to a **Routine** (inheriting the signature of `bb`) and removes `aa` from the constants list.
-   **Anonymous Callback Promotion**: Pascal requires named types for function pointers. When the extractor finds an "inline" callback in a C parameter, it promotes the anonymous pointer to a named Pascal type: `[Parent]_[Param]_cb`.
-   **Signature De-duplication**: To prevent type bloat, the tool uses a global registry to hash function signatures. Structurally identical anonymous callbacks share the same Pascal type name.
-   **Sugar-Aware Type Parsing**: 
    -   **For Parameters**: The tool stops "unwrapping" types when it hits a `typedef`. This ensures `EVP_MD_CTX *` remains `EVP_MD_CTX` (the "Sugar") rather than resolving to the internal struct name.
    -   **For Type Definitions**: The tool resolves the alias to its underlying structure to allow the generator to decide between a `record` or an `alias`.
-   **Array Decay**: Automatically identifies `Type[]` parameters as `pointer_depth: 1` using AST element unwrapping.

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

### File Output
-   **CRLF Enforcement**: The generator always enforces Windows-style line endings (`\r\n`) regardless of the host OS.

---

## 4. Data Flow Diagram

```text
[ OpenSSL Headers ]       [ .num / .syms ]
        |                        |
        +----------+-------------+
                   |
        [ Stage 1: C2Meta.py ] <--- (Clang AST)
                   |
        [ Language-Agnostic JSON ]
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

## 5. Design Philosophy: "Transparent & Defensive"
The toolchain follows a "Defensive Generation" philosophy. Templates check if a collection is empty before printing section headers (`type`, `var`, `const`). Combined with "Transparent Collision Management," this ensures that the resulting Pascal unit is always syntactically valid, while providing clear comments for any C identifiers that were suppressed due to Delphi's language constraints.
