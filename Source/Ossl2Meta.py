# =============================================================================
# C2Pas-Jinja Toolchain - Generator
#
# This software is released under the MIT License.
# See the LICENSE file in the project root for more information.
#
# Copyright (c) 2025 TaurusTLS Developers
# Developed with assistance from Google Gemini AI.
# =============================================================================

import os
import sys
import json
import re
import argparse
import clang.cindex

class OpenSSLExtractor:
    def __init__(self, num_symbols):
        self.num_symbols = num_symbols
        self.db = {
            "header": "", "types": [], "enums": [], 
            "callbacks": [], "constants": [], "routines": [], "ossl_stacks": []
        }
        self.processed_symbols = set()
        self.signature_registry = {} 
        self.current_parent = ""

    def get_source_snippet(self, node):
        if not node.extent.start.file: return ""
        try:
            with open(node.extent.start.file.name, 'rb') as f:
                f.seek(node.extent.start.offset)
                length = node.extent.end.offset - node.extent.start.offset
                return f.read(length).decode('utf-8', errors='ignore').strip()
        except: return ""

    def is_func_like_macro(self, node):
        tokens = list(node.get_tokens())
        if len(tokens) < 2: return False
        if tokens[1].spelling == '(':
            return tokens[1].extent.start.offset == tokens[0].extent.end.offset
        return False

    def get_signature_key(self, type_obj):
        canon = type_obj.get_canonical()
        if canon.kind == clang.cindex.TypeKind.POINTER:
            canon = canon.get_pointee()
        
        if canon.kind not in (clang.cindex.TypeKind.FUNCTIONPROTO, clang.cindex.TypeKind.FUNCTIONNOPROTO):
            return "unknown_sig"

        ret = self.parse_type_info(canon.get_result())
        ret_str = f"{ret['name']}{'*' * ret['pointer_depth']}"
        params = []
        if canon.kind == clang.cindex.TypeKind.FUNCTIONPROTO:
            for arg_type in canon.argument_types():
                p = self.parse_type_info(arg_type)
                params.append(f"{p['name']}{'*' * p['pointer_depth']}")
        return f"{ret_str}({','.join(params)})"

    def parse_type_info(self, type_obj, param_name=None, cursor=None):
        canon = type_obj.get_canonical()
        is_callback = False
        raw_func_type = None

        if canon.kind == clang.cindex.TypeKind.POINTER:
            pointee_canon = canon.get_pointee()
            if pointee_canon.kind in (clang.cindex.TypeKind.FUNCTIONPROTO, clang.cindex.TypeKind.FUNCTIONNOPROTO):
                is_callback = True
                # Use sugared pointee if type_obj is a pointer, otherwise use canonical
                raw_func_type = type_obj.get_pointee() if type_obj.kind == clang.cindex.TypeKind.POINTER else pointee_canon
        elif canon.kind in (clang.cindex.TypeKind.FUNCTIONPROTO, clang.cindex.TypeKind.FUNCTIONNOPROTO):
            is_callback = True
            raw_func_type = type_obj

        if is_callback and raw_func_type:
            is_typedef = type_obj.kind == clang.cindex.TypeKind.TYPEDEF
            sig_key = self.get_signature_key(type_obj)
            
            if is_typedef:
                cb_name = type_obj.spelling
            else:
                if sig_key in self.signature_registry:
                    return {"name": self.signature_registry[sig_key], "pointer_depth": 0, "is_callback": True}
                cb_name = f"{self.current_parent}_{param_name or 'func'}_cb"
            
            self.signature_registry[sig_key] = cb_name

            if not any(c['name'] == cb_name for c in self.db["callbacks"]):
                cb_params = []
                target_cursor = cursor or type_obj.get_declaration()
                param_cursors = [c for c in target_cursor.get_children() if c.kind == clang.cindex.CursorKind.PARM_DECL]
                
                if param_cursors:
                    for i, p_cur in enumerate(param_cursors):
                        cb_params.append({
                            "name": p_cur.spelling or f"arg{i+1}",
                            "type": self.parse_type_info(p_cur.type, cursor=p_cur)
                        })
                
                if not cb_params and raw_func_type.get_canonical().kind == clang.cindex.TypeKind.FUNCTIONPROTO:
                    for i, arg_type in enumerate(raw_func_type.get_canonical().argument_types()):
                        cb_params.append({"name": f"arg{i+1}", "type": self.parse_type_info(arg_type)})

                self.db["callbacks"].append({
                    "name": cb_name,
                    "return_type": self.parse_type_info(raw_func_type.get_result()),
                    "params": cb_params,
                    "is_promoted": not is_typedef,
                    "needs_attention": not is_typedef,
                    "c_decl": self.get_source_snippet(target_cursor) if is_typedef else f"Promoted from {self.current_parent}"
                })
            return {"name": cb_name, "pointer_depth": 0, "is_callback": True}

        pointer_depth = 0
        current_type = type_obj
        while current_type.kind in (
            clang.cindex.TypeKind.POINTER, clang.cindex.TypeKind.INCOMPLETEARRAY,
            clang.cindex.TypeKind.CONSTANTARRAY, clang.cindex.TypeKind.VARIABLEARRAY
        ):
            if current_type.kind == clang.cindex.TypeKind.TYPEDEF: break
            pointer_depth += 1
            if current_type.kind == clang.cindex.TypeKind.POINTER:
                current_type = current_type.get_pointee()
            else:
                current_type = current_type.get_array_element_type()

        name = current_type.spelling or current_type.get_canonical().spelling
        name = name.replace('const ', '').replace('struct ', '').replace('enum ', '').replace('union ', '').strip()
        name = name.split('(')[0].replace('*', '').strip()
        
        # Detect anonymous structs/unions used as fields
        if not name or '(' in name:
            decl = current_type.get_declaration()
            if decl.kind in (clang.cindex.CursorKind.STRUCT_DECL, clang.cindex.CursorKind.UNION_DECL):
                kind_str = "struct" if decl.kind == clang.cindex.CursorKind.STRUCT_DECL else "union"
                # Promote to a named type if we have context
                if self.current_parent and param_name:
                    name = f"{self.current_parent}_{param_name}_{kind_str}"
                    # Only add to global types if not already there
                    if not any(t['name'] == name for t in self.db["types"]):
                        fields = []
                        for child in decl.get_children():
                            if child.kind == clang.cindex.CursorKind.FIELD_DECL:
                                # Recursively parse field types, using the new name as parent context
                                old_parent = self.current_parent
                                self.current_parent = name
                                fields.append({
                                    "name": child.spelling,
                                    "type": self.parse_type_info(child.type, child.spelling, child)
                                })
                                self.current_parent = old_parent
                        
                        self.db["types"].append({
                            "name": name, "kind": kind_str, "is_opaque": False,
                            "fields": fields, "is_promoted": True,
                            "c_decl": self.get_source_snippet(decl)
                        })
                        self.processed_symbols.add(name)
                else:
                    name = "void" # Fallback for truly untrackable anonymous types

        return {"name": name, "pointer_depth": pointer_depth, "is_const": type_obj.is_const_qualified()}

    def post_process_aliases(self):
        """Moves constants that alias routines into the routines list."""
        routine_map = {r['name']: r for r in self.db["routines"]}
        new_constants = []
        for c in self.db["constants"]:
            target_name = c['value'].strip()
            if target_name in routine_map:
                target = routine_map[target_name]
                self.db["routines"].append({
                    "name": c['name'], "return_type": target["return_type"],
                    "params": target["params"], "is_macro": True, "is_inline": True,
                    "is_alias": True, "alias_target": target_name,
                    "introduced": target.get("introduced"), "deprecated": target.get("deprecated"),
                    "needs_attention": True,
                    "c_decl": c.get("c_decl")
                })
            else:
                new_constants.append(c)
        self.db["constants"] = new_constants

    def post_process_stacks(self):
        """Removes internal stack types and callbacks that are now covered by ossl_stacks."""
        stack_names = {s['name'] for s in self.db["ossl_stacks"]}
        if not stack_names: return

        def is_stack_related(name):
            if not name: return False
            for sn in stack_names:
                # Patterns: sk_TYPE_..., ossl_check_TYPE_..., stack_st_TYPE
                if name.startswith(f"sk_{sn}_") or \
                   name.startswith(f"ossl_check_{sn}_") or \
                   name == f"stack_st_{sn}":
                    return True
            return False

        # Filter all primary collections to remove redundant stack boilerplate
        self.db["callbacks"] = [x for x in self.db["callbacks"] if not is_stack_related(x['name'])]
        self.db["types"] = [x for x in self.db["types"] if not is_stack_related(x['name'])]
        self.db["routines"] = [x for x in self.db["routines"] if not is_stack_related(x['name'])]
        self.db["constants"] = [x for x in self.db["constants"] if not is_stack_related(x['name'])]

    def build(self, header_path, include_paths):
        index = clang.cindex.Index.create()
        self.db["header"] = os.path.basename(header_path)
        target_abs = os.path.realpath(header_path)
        tu = index.parse(header_path, args=[f'-I{p}' for p in include_paths] + ['-DOPENSSL_SUPPRESS_DEPRECATED'], 
                         options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        
        stack_macros = ('SKM_DEFINE_STACK_OF_INTERNAL', 'SKM_DEFINE_STACK_OF', 
                        'DEFINE_STACK_OF', 'DEFINE_STACK_OF_CONST', 'DEFINE_SPECIAL_STACK_OF')

        for node in tu.cursor.walk_preorder():
            if not node.location.file: continue
            if os.path.realpath(node.location.file.name) != target_abs: continue

            if node.kind == clang.cindex.CursorKind.MACRO_INSTANTIATION and node.spelling in stack_macros:
                snippet = self.get_source_snippet(node)
                # Extract the first argument as the stack type name (e.g. X509, CONF_VALUE)
                m = re.search(fr'{node.spelling}\s*\(\s*([^,\s\)]+)', snippet)
                if m:
                    stack_name = m.group(1)
                    target_stack = None
                    for s in self.db["ossl_stacks"]:
                        if s["name"] == stack_name:
                            target_stack = s
                            break
                    if not target_stack:
                        target_stack = {"name": stack_name, "decls": []}
                        self.db["ossl_stacks"].append(target_stack)
                    target_stack["decls"].append(snippet)

            elif node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.spelling in self.num_symbols:
                self.current_parent = node.spelling
                params = [{"name": arg.spelling or f"arg{i+1}", "type": self.parse_type_info(arg.type, arg.spelling, arg)} 
                          for i, arg in enumerate(node.get_arguments())]
                meta = self.num_symbols[node.spelling]
                self.db["routines"].append({
                    "name": node.spelling, "return_type": self.parse_type_info(node.result_type),
                    "params": params, "introduced": meta['introduced'], "deprecated": meta['deprecated'],
                    "is_macro": False, 
                    "needs_attention": node.is_definition(),
                    "c_decl": self.get_source_snippet(node)
                })
                self.processed_symbols.add(node.spelling)

            elif node.kind == clang.cindex.CursorKind.MACRO_DEFINITION:
                name = node.spelling

                # Special handling for OSSL Stack macros and checks (sk_XXX_..., ossl_check_XXX_...)
                if name.startswith('sk_') or name.startswith('ossl_check_'):
                    for stack in self.db["ossl_stacks"]:
                        sn = stack['name']
                        if name.startswith(f"sk_{sn}_") or name.startswith(f"ossl_check_{sn}_"):
                            stack["decls"].append(self.get_source_snippet(node))
                            self.processed_symbols.add(name)
                            break

                if name in self.num_symbols and name not in self.processed_symbols:
                    if self.is_func_like_macro(node):
                        tokens = list(node.get_tokens())
                        macro_params = []
                        i = 2
                        while i < len(tokens) and tokens[i].spelling != ')':
                            if tokens[i].spelling != ',': macro_params.append(tokens[i].spelling)
                            i += 1
                        meta = self.num_symbols[name]
                        self.db["routines"].append({
                            "name": name, "return_type": {"name": "int", "pointer_depth": 0, "is_const": False, "is_guess": True},
                            "params": [{"name": p, "type": {"name": "Pointer", "pointer_depth": 0, "is_const": False, "is_guess": True}} for p in macro_params],
                            "is_macro": True, "is_inline": True, "introduced": meta["introduced"], "deprecated": meta["deprecated"],
                            "needs_attention": True,
                            "c_decl": self.get_source_snippet(node)
                        })
                        self.processed_symbols.add(name)
                    else:
                        # Not function-like: Treat as constant even if in num_symbols
                        # It will be caught by the general macro-constant logic below
                        pass

                if name not in self.processed_symbols:
                    tokens = list(node.get_tokens())
                    if len(tokens) > 1 and not self.is_func_like_macro(node):
                        body = "".join([t.spelling for t in tokens[1:] if t.kind != clang.cindex.TokenKind.COMMENT])
                        if body.strip():
                            self.db["constants"].append({"name": name, "value": body.strip(), "c_decl": self.get_source_snippet(node)})
                    self.processed_symbols.add(name)

            elif node.kind == clang.cindex.CursorKind.TYPEDEF_DECL:
                self.current_parent = node.spelling
                underlying = node.underlying_typedef_type
                canon = underlying.get_canonical()
                # Check if this typedef wraps an enum (e.g. typedef enum FOO {...} FOO;)
                if canon.kind == clang.cindex.TypeKind.ENUM and node.spelling not in self.processed_symbols:
                    entries = []
                    for child in node.get_children():
                        if child.kind == clang.cindex.CursorKind.ENUM_DECL:
                            for val in child.get_children():
                                if val.kind == clang.cindex.CursorKind.ENUM_CONSTANT_DECL:
                                    entries.append({"name": val.spelling, "value": val.enum_value})
                    self.db["enums"].append({"name": node.spelling, "entries": entries, "c_decl": self.get_source_snippet(node)})
                    self.processed_symbols.add(node.spelling)
                else:
                    type_info = self.parse_type_info(node.type, cursor=node)
                    if not type_info.get('is_callback') and node.spelling not in self.processed_symbols:
                        # Skip self-referencing aliases (e.g. typedef DH_METHOD dh_method -> already named the same)
                        if node.spelling != type_info.get('name'):
                            self.db["types"].append({"name": node.spelling, "kind": "alias", "parent_type": type_info, "c_decl": self.get_source_snippet(node)})
                        self.processed_symbols.add(node.spelling)


            elif node.kind in (clang.cindex.CursorKind.STRUCT_DECL, clang.cindex.CursorKind.UNION_DECL):
                # Skip truly anonymous types or Clang-generated "unnamed at" placeholders
                if node.spelling and "(unnamed at" not in node.spelling and node.spelling not in self.processed_symbols:
                    fields = []
                    needs_attention = (node.kind == clang.cindex.CursorKind.UNION_DECL)
                    if node.is_definition():
                        for child in node.get_children():
                            if child.kind == clang.cindex.CursorKind.FIELD_DECL:
                                # Check if field is a union
                                f_type_canon = child.type.get_canonical()
                                if f_type_canon.kind == clang.cindex.TypeKind.RECORD:
                                    f_decl = f_type_canon.get_declaration()
                                    if f_decl.kind == clang.cindex.CursorKind.UNION_DECL:
                                        needs_attention = True

                                fields.append({
                                    "name": child.spelling,
                                    "type": self.parse_type_info(child.type, cursor=child)
                                })

                    if needs_attention: fields = []

                    self.db["types"].append({
                        "name": node.spelling, 
                        "kind": "struct" if node.kind == clang.cindex.CursorKind.STRUCT_DECL else "union",
                        "is_opaque": not node.is_definition(), 
                        "fields": fields,
                        "needs_attention": needs_attention,
                        "c_decl": self.get_source_snippet(node)
                    })
                    self.processed_symbols.add(node.spelling)

        self.post_process_aliases()
        self.post_process_stacks()
        return self.db

def parse_exports(num_files, sym_files, legacy_num_files=[]):
    history = {}
    # 1. Build history from legacy versions (e.g. 1.1.1)
    for f in legacy_num_files:
        if not os.path.exists(f): continue
        with open(f, 'r') as src:
            for line in src:
                p = line.split()
                if len(p) >= 4 and 'FUNCTION' in p[3]:
                    history[p[0]] = p[2].replace('.','_')

    symbols = {}
    # 2. Parse main .num files
    for f in num_files:
        if not os.path.exists(f): continue
        with open(f, 'r') as src:
            for line in src:
                p = line.split()
                if len(p) >= 4 and 'FUNCTION' in p[3]:
                    name = p[0]
                    intro_ver = p[2].replace('.','_')
                    dep = re.search(r'DEPRECATEDIN_(\d+)_(\d+)', p[3])
                    dep_ver = f"{dep.group(1)}_{dep.group(2)}_0" if dep else None
                    
                    # ENRICHMENT: If version is generic 3.0.0, check history
                    if intro_ver == "3_0_0" and name in history:
                        intro_ver = history[name]
                        
                    symbols[name] = {'introduced': intro_ver, 'deprecated': dep_ver}

    # 3. Parse .syms files (for macro aliases)
    for f in sym_files:
        if not os.path.exists(f): continue
        with open(f, 'r') as src:
            for line in src:
                p = line.split()
                if p and p[0] not in symbols:
                    name = p[0]
                    intro_ver = '3_0_0'
                    dep_ver = None
                    if 'deprecated' in p:
                        idx = p.index('deprecated')
                        if len(p) > idx + 1: dep_ver = p[idx+1].replace('.','_')
                    
                    # ENRICHMENT: Even for macros, check legacy history
                    if name in history:
                        intro_ver = history[name]
                        
                    symbols[name] = {'introduced': intro_ver, 'deprecated': dep_ver}
    return symbols

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="Root of OpenSSL source tree (e.g. 3.x)")
    parser.add_argument("--header", required=True, help="Header filename only (e.g. ssl.h, evp.h)")
    parser.add_argument("--legacy", help="Directory containing legacy .num files (e.g. 1.1.1 versions of libcrypto.num/libssl.num)")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--search", action='append', help="Optional additional include search paths")
    parser.add_argument("--force", action='store_true', help="Force creation of JSON output even if no symbols were extracted")
    args = parser.parse_args()

    # 1. Resolve primary paths
    header_path = os.path.join(args.root, 'include', 'openssl', args.header)
    include_paths = [os.path.join(args.root, 'include')]
    if args.search: include_paths.extend(args.search)

    # 2. Resolve main symbol files
    num_files = [
        os.path.join(args.root, 'util', 'libcrypto.num'),
        os.path.join(args.root, 'util', 'libssl.num')
    ]
    sym_files = []
    other_syms = os.path.join(args.root, 'util', 'other.syms')
    if os.path.exists(other_syms): sym_files.append(other_syms)

    # 3. Resolve legacy symbol files
    legacy_nums = []
    if args.legacy:
        for n in ['libcrypto.num', 'libssl.num']:
            lpath = os.path.join(args.legacy, n)
            if os.path.exists(lpath): legacy_nums.append(lpath)
        # Check for optional legacy syms
        lsyms = os.path.join(args.legacy, 'other.syms')
        if os.path.exists(lsyms): sym_files.append(lsyms) # Add to sym_files for enrichment

    if not os.path.exists(header_path):
        print(f"Error: Header not found at {header_path}")
        sys.exit(1)

    exports = parse_exports(num_files, sym_files, legacy_nums)
    extractor = OpenSSLExtractor(exports)
    db = extractor.build(header_path, include_paths)
    
    # Calculate specific counts
    macro_routines = sum(1 for r in db['routines'] if r.get('is_macro'))
    func_routines = len(db['routines']) - macro_routines
    promoted_cbs = sum(1 for c in db['callbacks'] if c.get('is_promoted'))
    
    has_data = any([db['types'], db['enums'], db['callbacks'], db['constants'], db['routines']])
    
    print("\n" + "="*50)
    print(f"Ossl2Meta EXTRACTION COMPLETE")
    print("="*50)
    print(f"Source Header: {db['header']}")
    
    if not has_data and not args.force:
        print(f"Output JSON:   SKIPPED (No data extracted, use --force to override)")
        sys.exit(254)
    else:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2)
        print(f"Output JSON:   {args.out}")
        
    print("-" * 50)
    print(f"Routines:      {len(db['routines']):>4} ({func_routines} functions, {macro_routines} macro aliases)")
    print(f"Types:         {len(db['types']):>4}")
    print(f"Enums:         {len(db['enums']):>4}")
    print(f"Constants:     {len(db['constants']):>4}")
    print(f"Callbacks:     {len(db['callbacks']):>4} ({promoted_cbs} promoted from anonymous pointers)")
    print(f"Ossl Stacks:   {len(db['ossl_stacks']):>4}")
    print("="*50 + "\n")
