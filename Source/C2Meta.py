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
            "callbacks": [], "constants": [], "routines": []
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
        ret = self.parse_type_info(canon.get_result())
        ret_str = f"{ret['name']}{'*' * ret['pointer_depth']}"
        params = []
        for arg_type in canon.argument_types():
            p = self.parse_type_info(arg_type)
            params.append(f"{p['name']}{'*' * p['pointer_depth']}")
        return f"{ret_str}({','.join(params)})"

    def parse_type_info(self, type_obj, param_name=None):
        canon = type_obj.get_canonical()
        is_callback = False
        raw_func_type = None

        if canon.kind == clang.cindex.TypeKind.POINTER:
            pointee_canon = canon.get_pointee()
            if pointee_canon.kind in (clang.cindex.TypeKind.FUNCTIONPROTO, clang.cindex.TypeKind.FUNCTIONNOPROTO):
                is_callback = True
                raw_func_type = type_obj.get_pointee() 
        elif canon.kind in (clang.cindex.TypeKind.FUNCTIONPROTO, clang.cindex.TypeKind.FUNCTIONNOPROTO):
            is_callback = True
            raw_func_type = type_obj

        if is_callback and raw_func_type:
            if type_obj.kind == clang.cindex.TypeKind.TYPEDEF:
                return {"name": type_obj.spelling, "pointer_depth": 0, "is_callback": True}
            
            sig_key = self.get_signature_key(type_obj)
            if sig_key in self.signature_registry:
                return {"name": self.signature_registry[sig_key], "pointer_depth": 0, "is_callback": True}
            
            cb_name = f"{self.current_parent}_{param_name or 'func'}_cb"
            self.signature_registry[sig_key] = cb_name
            
            cb_params = []
            try:
                for i, arg_type in enumerate(raw_func_type.argument_types()):
                    cb_params.append({"name": f"arg{i+1}", "type": self.parse_type_info(arg_type)})
            except: pass

            self.db["callbacks"].append({
                "name": cb_name,
                "return_type": self.parse_type_info(raw_func_type.get_result()),
                "params": cb_params,
                "is_promoted": True,
                "c_decl": f"Promoted from {self.current_parent}"
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
                    "c_decl": c.get("c_decl")
                })
            else:
                new_constants.append(c)
        self.db["constants"] = new_constants

    def build(self, header_path, include_paths):
        index = clang.cindex.Index.create()
        self.db["header"] = os.path.basename(header_path)
        target_abs = os.path.realpath(header_path)
        tu = index.parse(header_path, args=[f'-I{p}' for p in include_paths] + ['-DOPENSSL_SUPPRESS_DEPRECATED'], 
                         options=clang.cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        
        for node in tu.cursor.walk_preorder():
            if not node.location.file: continue
            if os.path.realpath(node.location.file.name) != target_abs: continue

            if node.kind == clang.cindex.CursorKind.FUNCTION_DECL and node.spelling in self.num_symbols:
                self.current_parent = node.spelling
                params = [{"name": arg.spelling or f"arg{i+1}", "type": self.parse_type_info(arg.type, arg.spelling)} 
                          for i, arg in enumerate(node.get_arguments())]
                meta = self.num_symbols[node.spelling]
                self.db["routines"].append({
                    "name": node.spelling, "return_type": self.parse_type_info(node.result_type),
                    "params": params, "introduced": meta['introduced'], "deprecated": meta['deprecated'],
                    "is_macro": False, "c_decl": self.get_source_snippet(node)
                })
                self.processed_symbols.add(node.spelling)

            elif node.kind == clang.cindex.CursorKind.MACRO_DEFINITION:
                name = node.spelling
                if name in self.num_symbols and name not in self.processed_symbols:
                    tokens = list(node.get_tokens())
                    macro_params = []
                    if self.is_func_like_macro(node):
                        i = 2
                        while i < len(tokens) and tokens[i].spelling != ')':
                            if tokens[i].spelling != ',': macro_params.append(tokens[i].spelling)
                            i += 1
                    meta = self.num_symbols[name]
                    self.db["routines"].append({
                        "name": name, "return_type": {"name": "int", "pointer_depth": 0, "is_const": False, "is_guess": True},
                        "params": [{"name": p, "type": {"name": "Pointer", "pointer_depth": 0, "is_const": False, "is_guess": True}} for p in macro_params],
                        "is_macro": True, "is_inline": True, "introduced": meta["introduced"], "deprecated": meta["deprecated"],
                        "c_decl": self.get_source_snippet(node)
                    })
                    self.processed_symbols.add(name)
                elif name not in self.processed_symbols:
                    tokens = list(node.get_tokens())
                    if len(tokens) > 1 and not self.is_func_like_macro(node):
                        body = "".join([t.spelling for t in tokens[1:]])
                        if body.strip():
                            self.db["constants"].append({"name": name, "value": body.strip(), "c_decl": self.get_source_snippet(node)})
                    self.processed_symbols.add(name)

            elif node.kind == clang.cindex.CursorKind.TYPEDEF_DECL:
                self.current_parent = node.spelling
                type_info = self.parse_type_info(node.underlying_typedef_type)
                if not type_info.get('is_callback') and node.spelling not in self.processed_symbols:
                    self.db["types"].append({"name": node.spelling, "kind": "alias", "parent_type": type_info, "c_decl": self.get_source_snippet(node)})
                    self.processed_symbols.add(node.spelling)

            elif node.kind in (clang.cindex.CursorKind.STRUCT_DECL, clang.cindex.CursorKind.UNION_DECL):
                if node.spelling and node.spelling not in self.processed_symbols:
                    self.db["types"].append({"name": node.spelling, "kind": "struct" if node.kind == clang.cindex.CursorKind.STRUCT_DECL else "union",
                                             "is_opaque": not node.is_definition(), "c_decl": self.get_source_snippet(node)})
                    self.processed_symbols.add(node.spelling)

        self.post_process_aliases()
        return self.db

def parse_exports(num_files, sym_files):
    symbols = {}
    for f in num_files:
        if not os.path.exists(f): continue
        with open(f, 'r') as src:
            for line in src:
                p = line.split()
                if len(p) >= 4 and 'FUNCTION' in p[3]:
                    dep = re.search(r'DEPRECATEDIN_(\d+)_(\d+)', p[3])
                    dep_ver = f"{dep.group(1)}_{dep.group(2)}_0" if dep else None
                    symbols[p[0]] = {'introduced': p[2].replace('.','_'), 'deprecated': dep_ver}
    for f in sym_files:
        if not os.path.exists(f): continue
        with open(f, 'r') as src:
            for line in src:
                p = line.split()
                if p and p[0] not in symbols:
                    dep_ver = None
                    if 'deprecated' in p:
                        idx = p.index('deprecated')
                        if len(p) > idx + 1: dep_ver = p[idx+1].replace('.','_')
                    symbols[p[0]] = {'introduced': '3_0_0', 'deprecated': dep_ver}
    return symbols

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--header", required=True); parser.add_argument("--search", action='append', required=True)
    parser.add_argument("--num", action='append', required=True); parser.add_argument("--syms", action='append', required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--force", action='store_true', help="Force creation of JSON output even if no symbols were extracted")
    args = parser.parse_args()

    exports = parse_exports(args.num, args.syms)
    extractor = OpenSSLExtractor(exports)
    db = extractor.build(args.header, args.search)
    
    # Calculate specific counts
    macro_routines = sum(1 for r in db['routines'] if r.get('is_macro'))
    func_routines = len(db['routines']) - macro_routines
    promoted_cbs = sum(1 for c in db['callbacks'] if c.get('is_promoted'))
    
    has_data = any([db['types'], db['enums'], db['callbacks'], db['constants'], db['routines']])
    
    print("\n" + "="*50)
    print(f"C2Meta EXTRACTION COMPLETE")
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
    print("="*50 + "\n")