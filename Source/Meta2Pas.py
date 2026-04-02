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
        name = info['name']
        depth = info.get('pointer_depth', 0)
        mapping = self.type_map.get(name, name)
        if isinstance(mapping, dict):
            depth_key = str(depth)
            if depth_key in mapping: return mapping[depth_key]
            base = mapping.get("0", name)
        else: base = mapping
        if depth == 0: return base
        if depth == 1:
            if base == 'Void': return "Pointer"
            return "P" + base if not (base.startswith('P') and len(base) > 1 and base[1].isupper()) else "P" + base
        if depth == 2:
            return "PP" + base
        return ("P" * depth) + base

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
    
    with open(args.out, "w", encoding="utf-8") as f: f.write(output)

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