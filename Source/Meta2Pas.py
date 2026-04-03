# =============================================================================
# C2Pas-Jinja Toolchain - Generator
#
# This software is released under the MIT License.
# See the LICENSE file in the project root for more information.
#
# Copyright (c) 2025 TaurusTLS Developers
# Developed with assistance from Google Gemini AI.
# =============================================================================

import json
import argparse
import re
import os
from jinja2 import Environment, FileSystemLoader

class Generator:
    def __init__(self, type_map_path, escape_symbol='_'): # Default to '_'
        if os.path.exists(type_map_path):
            with open(type_map_path, 'r') as f:
                self.type_map = json.load(f)
        else:
            self.type_map = {}
            
        self.escape_symbol = escape_symbol
        self.reserved = {
            'type', 'var', 'procedure', 'function', 'record', 'end', 'begin', 'if', 
            'then', 'else', 'while', 'do', 'repeat', 'until', 'for', 'to', 'downto', 
            'in', 'is', 'as', 'class', 'interface', 'implementation', 'unit', 'program', 
            'library', 'uses', 'const', 'property', 'raise', 'try', 'except', 'finally', 
            'label', 'goto', 'exit', 'break', 'continue', 'mod', 'div', 'not', 'and', 
            'or', 'xor', 'shl', 'shr', 'set', 'file', 'object', 'packed', 'asm', 
            'inherited', 'initialization', 'finalization', 'resourcestring', 'threadvar', 'out'
        }

    def pas_name(self, name):
        """Sanitizes Delphi reserved words using the chosen escape symbol."""
        if not name: return ""
        if name.lower() in self.reserved:
            return f"{self.escape_symbol}{name}"
        return name
    
    def pas_type(self, info):
        """
        Translates C type info to Pascal types.
        Priority:
        1. Exact depth match in typemap.json.
        2. If name is 'Pointer', return 'Pointer' (Depth 0/1) or 'PPointer' (Depth 2+).
        3. If depth 0 and unmapped: Prepend 'T'.
        4. If depth > 0: Hierarchical prefixing (P, PP) with T->P replacement.
        """
        name = info.get('name', 'int')
        target_depth = info.get('pointer_depth', 0)
        mapping = self.type_map.get(name, name)

        # Determine if the type is explicitly mapped in typemap.json
        is_mapped = name in self.type_map
        
        # Resolve base type and check for exact depth match
        if isinstance(mapping, dict):
            depth_key = str(target_depth)
            if depth_key in mapping:
                return mapping[depth_key] # Return exact match (e.g. PByte)
            base_type = mapping.get("0", name)
        else:
            base_type = mapping

        # 1. Handle Depth 0 (Base Type)
        if target_depth == 0:
            # EXCEPTION: Never prefix 'Pointer' with 'T'
            if base_type == 'Pointer':
                return 'Pointer'
                
            if not is_mapped:
                # Add T prefix to unmapped C types (e.g. asn1_object_st -> Tasn1_object_st)
                if not (base_type.startswith('T') and len(base_type) > 1 and base_type[1].isupper()):
                    return "T" + base_type
            return base_type

        # 2. Handle Pointers (Depth > 0)
        # Find the highest defined depth M < target_depth
        base_depth = 0
        if isinstance(mapping, dict):
            defined_depths = sorted([int(k) for k in mapping.keys()], reverse=True)
            for d in defined_depths:
                if d < target_depth:
                    base_depth = d
                    base_type = mapping[str(d)]
                    break

        # EXCEPTION: Handle 'Void' and 'Pointer' identically for pointer logic
        # void* -> Pointer, void** -> PPointer
        # Pointer (depth 1) -> Pointer, Pointer* (depth 2) -> PPointer
        if base_type == 'Void' or base_type == 'Pointer':
            res = "Pointer"
            for _ in range(target_depth - 1):
                res = "P" + res
            return res

        # If we are starting from depth 0 (unmapped or mapped base)
        if base_depth == 0:
            # Apply T->P replacement logic
            if not is_mapped and not (base_type.startswith('T') and len(base_type) > 1 and base_type[1].isupper()):
                # Unmapped: asn1_object_st -> Pasn1_object_st
                res = "P" + base_type
            elif base_type.startswith('T') and len(base_type) > 1 and base_type[1].isupper():
                # Mapped: TIdC_INT -> PIdC_INT
                res = "P" + base_type[1:]
            else:
                # Other: Integer -> PInteger
                res = "P" + base_type
            
            # Add remaining P prefixes for depths > 1
            for _ in range(target_depth - 1):
                res = "P" + res
            return res
        else:
            # Build from an existing pointer mapping (e.g. depth 1 PByte -> depth 2 PPByte)
            res = base_type
            for _ in range(target_depth - base_depth):
                res = "P" + res
            return res
        
    def pas_version(self, ver_str):
        if not ver_str: return None
        p = str(ver_str).replace('.', '_').split('_')
        while len(p) < 3: p.append('0')
        return f"(byte({p[0]}) shl 8 or byte({p[1]})) shl 8 or byte({p[2]})"

    def pas_expression(self, val):
        if not val: return ""
        val = str(val).replace("'", "''").replace('"', "'")
        val = re.sub(r'0[xX]([0-9a-fA-F]+)', r'$\1', val)
        val = val.replace('<<', ' shl ').replace('>>', ' shr ').replace('|', ' or ').replace('&', ' and ')
        val = val.replace('~', ' not ').replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ')
        val = re.sub(r'([0-9]+)[UL]+', r'\1', val)
        return re.sub(r'\s+', ' ', val).strip()

    def pas_sig(self, r, is_var=False, prefix=""):
        ret = self.pas_type(r['return_type'])
        params = []
        for p in r['params']:
            p_type = self.pas_type(p['type'])
            pref = "const " if p['type'].get('is_const') and p['type'].get('pointer_depth', 0) > 0 else ""
            params.append(f"{pref}{self.pas_name(p['name'])}: {p_type}")
        p_str = f"({'; '.join(params)})" if params else ""
        name = prefix + r['name']
        if ret == 'Void':
            return f"procedure{p_str}; cdecl" if is_var else f"procedure {name}{p_str}; cdecl"
        return f"function{p_str}: {ret}; cdecl" if is_var else f"function {name}{p_str}: {ret}; cdecl"

def version_val_filter(value):
    if not value: return 0
    parts = [int(x) for x in str(value).replace('.', '_').split('_') if x.isdigit()]
    while len(parts) < 3: parts.append(0)
    return (parts[0] << 16) | (parts[1] << 8) | parts[2]

def match_test(value, pattern):
    if value is None: return False
    return bool(re.search(pattern, str(value)))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TaurusTLS Pascal Generator")
    parser.add_argument("--json", required=True)
    parser.add_argument("--template", required=True)
    parser.add_argument("--type-map", required=True)
    parser.add_argument("--out", required=True)
    # Add the escape symbol argument with restricted choices
    parser.add_argument("--escape-symbol", choices=['_', '&'], default='_', help="Symbol to escape reserved words ('_' or '&')")
    args = parser.parse_args()

    with open(args.json, 'r', encoding='utf-8') as f: db = json.load(f)
    # Pass the argument to your Generator
    gen = Generator(args.type_map, args.escape_symbol)

    # Define local variables for the status print
    routines = [r for r in db['routines'] if not r.get('is_macro') and not r.get('is_inline')]
    static_routines = [r for r in db['routines'] if r.get('is_macro') or r.get('is_inline')]
    types = db.get('types', [])
    enums = db.get('enums', [])
    constants = db.get('constants', [])
    callbacks = db.get('callbacks', [])

    env = Environment(loader=FileSystemLoader("."), trim_blocks=True, lstrip_blocks=True)
    env.filters.update({'pas_name': gen.pas_name, 'pas_type': gen.pas_type, 'pas_version': gen.pas_version, 'pas_expression': gen.pas_expression, 'pas_sig': gen.pas_sig, 'version_val': version_val_filter})
    env.tests.update({'match': match_test})
    
    template = env.get_template(args.template)
    output = template.render(header=db.get('header', 'unknown.h'), routines=routines, static_routines=static_routines, callbacks=callbacks, constants=constants, types=types, enums=enums)
    
    with open(args.out, "w", encoding="utf-8", newline='\r\n') as f: f.write(output)

    print("\n" + "="*50)
    print(f"C2PAS-JINJA GENERATION COMPLETE")
    print("="*50)
    print(f"Output Unit:   {args.out}")
    print("-" * 50)
    print(f"ENTITIES PASSED TO TEMPLATE:")
    print(f"  Routines:    {len(routines):>4}")
    print(f"  Inlines:     {len(static_routines):>4}")
    print(f"  Types:       {len(types):>4}")
    print(f"  Enums:       {len(enums):>4}")
    print(f"  Constants:   {len(constants):>4}")
    print(f"  Callbacks:   {len(callbacks):>4}")
    print("="*50 + "\n")