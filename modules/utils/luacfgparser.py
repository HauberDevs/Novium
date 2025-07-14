import re
import ast

def parse_lua_cfg(path):
    with open(path, 'r', encoding='cp1252') as f:
        lua = f.read()

    # Replace Lua booleans
    lua = lua.replace('true', 'True').replace('false', 'False')

    # Remove inline comments
    def strip_inline_comments(text):
        result = []
        for line in text.splitlines():
            newline = ''
            in_str = False
            str_char = ''
            i = 0
            while i < len(line):
                c = line[i]
                if c in ('"', "'"):
                    if not in_str:
                        in_str = True
                        str_char = c
                    elif str_char == c:
                        in_str = False
                    newline += c
                elif not in_str and line[i:i+2] == '--':
                    break
                elif not in_str and c == '#':
                    break
                else:
                    newline += c
                i += 1
            if newline.strip():
                result.append(newline)
        return '\n'.join(result)

    lua = strip_inline_comments(lua)

    # Replace keys to JSON-style
    lua = re.sub(r"'([^']+)'\s*=", r'"\1":', lua)
    lua = re.sub(r'\["([^"]+)"\]\s*=', r'"\1":', lua)
    lua = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=', r'"\1":', lua)
    lua = re.sub(r',\s*([\]}])', r'\1', lua)

    try:
        return ast.literal_eval(lua)
    except Exception as e:
        raise ValueError("Failed to parse pseudo-Lua config: %s\nParsed text:\n%s" % (e, lua))

def load(path):
    return parse_lua_cfg(path)

def _format_value(v, indent=0):
    pad = '    ' * indent
    if isinstance(v, bool):
        return 'true' if v else 'false'
    elif isinstance(v, dict):
        lines = []
        lines.append('{')
        for k, val in v.items():
            lines.append(pad + '    %s = %s,' % (k, _format_value(val, indent+1)))
        lines.append(pad + '}')
        return '\n'.join(lines)
    elif isinstance(v, str):
        # Escape backslashes and double quotes for Lua string
        escaped = v.replace('\\', '\\\\').replace('"', '\\"')
        return '"%s"' % escaped
    else:
        return str(v)

def save(config, path):
    with open(path, 'w', encoding='cp1252') as f:
        f.write(_format_value(config))
