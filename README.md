# C2Pas-Jinja

**C2Pas-Jinja** is a high-fidelity, two-stage toolchain designed to transform complex C headers into production-ready Delphi/Pascal bindings. By decoupling the extraction of C metadata from the final code generation, it provides a flexible and robust way to maintain modern Pascal libraries.

Originally developed for the [TaurusTLS](https://github.com/TaurusTLS-Developers/TaurusTLS) project to support **OpenSSL 3.6+**, this toolchain is specifically engineered to handle the intricate patterns found in modern C APIs that traditional header converters often fail to process correctly.

## Core Architecture

The toolchain operates in two distinct phases:

1.  **Extraction (`ast2json.py`)**: Uses the **Clang AST** (Abstract Syntax Tree) library to parse C headers into a comprehensive, language-agnostic **JSON format**. This intermediate "database" captures types, constants, enums, and routines in a way that allows for the accurate reconstruction of the API in other languages.
2.  **Generation (`json2pas.py`)**: Utilizes the **Jinja2 template language** to transform the JSON metadata into Pascal units. This ensures that the logic of the output is entirely decoupled from the parser.

## Key Features

- **Clang AST Extraction**: Leverages `libclang` to ensure 100% accuracy in parsing C syntax, including complex macros and nested structures.
- **Jinja2 Templating Engine**: Provides total control over the generated code. You can change the Pascal coding style, indentation, or linking logic by simply editing a `.j2` template without touching the Python source code.
- **Anonymous Callback Promotion**: Automatically detects "inline" function pointers in C parameters and promotes them to named Pascal `callback` types, including global signature-based de-duplication.
- **Sugar-Aware Type Parsing**: Preserves C `typedef` aliases ("Sugar") in function parameters and return types, ensuring the generated Pascal API matches the original C documentation while correctly resolving underlying structures for type definitions.
- **Advanced Type Mapping**: Supports an external JSON-based type map with explicit pointer-depth overrides. This allows for precise mapping, such as translating `unsigned char *` specifically to `PByte` while `unsigned char` remains `Byte`.
- **OpenSSL Metadata Integration**: Native support for parsing `.num` and `other.syms` files to extract introduction/deprecation versions and filter exported symbols based on the OpenSSL lifecycle.
- **Intelligent Array Decay**: Correctly identifies C array parameters (`Type[]`) as pointers (`pointer_depth: 1`) using AST unwrapping rather than simple string parsing.

## Project Structure

```text
C2Pas-Jinja/
├── Source/
│   ├── ast2json.py    # The Clang-based AST Extractor
│   └── json2pas.py    # The Jinja2-based Pascal Generator
├── Examples/
│   ├── delphi_map.json # Standard C-to-Delphi type mappings
│   └── taurustls.j2    # Sample TaurusTLS-style template
├── Doc/
│   ├── Usage.md       # Detailed command-line instructions
│   └── Architecture.md # Technical outline of the pipeline
└── LICENSE            # MIT License
```

## Quick Start

### 1. Extract C Header to JSON
```bash
python Source/ast2json.py \
  --header /path/to/openssl/evp.h \
  --search /path/to/openssl/include \
  --num /path/to/utlils/libcrypto.num \
  --syms /path/to/utlils/other.syms \
  --out evp.json
```

### 2. Generate Pascal Unit
```bash
python Source/json2pas.py \
  --json evp.json \
  --template Examples/taurustls.j2 \
  --type-map Examples/delphi_map.json \
  --out TaurusTLSHeaders_evp.pas
```

## Prerequisites

- **Python 3.10+**
- **LLVM/Clang**: Ensure `libclang` is installed on your system.
- **Python Dependencies**:
  ```bash
  pip install clang jinja2
  ```

## License

This project is licensed under the **MIT License**. See the [LICENSE](LICENSE) file for the full text.

## Credits & Acknowledgments

- **Author:** [TaurusTLS Developers](https://github.com/TaurusTLS-Developers)
- **Architectural Assistance:** The core logic of this toolchain—including the Clang AST extraction patterns, anonymous callback promotion, and the Jinja2 filtering engine—was architected and implemented with the assistance of **Google Gemini AI**.
