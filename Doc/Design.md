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
-   `crypto/`: Contains internal headers (if needed for specific structural analysis).

---

## 2. Stage 1: The Extractor (`C2Meta.py`)

The extractor's job is to turn a C header into a language-agnostic "API Database" in JSON format.

### Clang AST Analysis
The tool uses `libclang` to parse the header. Unlike regex-based tools, this understands C scoping, macro expansion, and type decay.

### Key Logic Modules
-   **Export Resolver**: Cross-references every function found in the AST against OpenSSL's `.num` and `.syms` files. If a function isn't exported, it is ignored.
-   **Anonymous Callback Promotion**: Pascal requires named types for function pointers. When the extractor finds an "inline" callback in a C parameter, it promotes the anonymous pointer to a named Pascal type: `[Parent]_[Param]_cb`.
-   **Sugar-Aware Type Parsing**: 
    -   **For Parameters**: The tool stops "unwrapping" types when it hits a `typedef`. This ensures `EVP_MD_CTX *` remains `EVP_MD_CTX` (the "Sugar").
    -   **For Type Definitions**: The tool resolves the alias to its underlying structure to allow the generator to decide between a `record` or an `alias`.
-   **Array Decay**: Automatically identifies `Type[]` parameters as `pointer_depth: 1`.

---

## 3. Stage 2: The Generator (`Meta2Pas.py`)

The generator consumes the JSON database and applies a Jinja2 template to produce the final `.pas` unit.

### The Type Mapping Engine
The generator uses an external `delphi_map.json`. This map supports **Explicit Depth Overrides**:
-   **Simple Map**: `int` -> `Integer`. (Implicitly makes `int*` -> `PInteger`).
-   **Depth Map**: `unsigned char` with depth `1` -> `PByte`. 

### Identifier Escaping
The generator supports a `--escape-symbol` argument (`_` or `&`). 
-   Using `&` allows for native Delphi/FPC identifier escaping (e.g., `&to`, `&type`), which preserves the original C name in the binary while satisfying Pascal compiler rules.

### Jinja2 Custom Extensions
-   `version_val`: Converts version strings (e.g., `3_0_0`) into integers for numeric comparison.
-   `pas_sig`: Assembles C parameters and return types into a valid Delphi `function` or `procedure` signature.
-   `pas_expression`: Translates C hex (`0x`/`0X`) to Pascal (`$`) and bitwise operators.

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
[ Jinja2 Template ]      [ delphi_map.json ]
        |                        |
        +----------+-------------+
                   |
        [ Stage 2: Meta2Pas.py ]
                   |
        [ Final Pascal Unit (.pas) ]
```

## 5. Design Philosophy: "Defensive Generation"
The toolchain follows a "Defensive Generation" philosophy. The templates are designed to check if a collection (like `types` or `routines`) is empty before printing a section header (`type`, `var`, `const`). This ensures that if a header is filtered down to nothing (e.g., everything was deprecated before version 3.0), the resulting Pascal unit is still syntactically valid and does not contain empty declarations.