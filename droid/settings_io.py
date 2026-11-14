"""Small, layout-preserving updates of top-level values in settings.json."""

import json
import os
import re

_SCALAR = r'("(?:[^"\\]|\\.)*"|true|false|null|-?\d+(?:\.\d+)?)'


def _value_span(text, start):
    """End index of the JSON value starting at `start` (object/array via bracket matching)."""
    opener = text[start]
    if opener not in "{[":
        m = re.compile(_SCALAR).match(text, start)
        return m.end() if m else None
    closer = "}" if opener == "{" else "]"
    depth, i, in_str = 0, start, False
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return None


def _format(value, level=1):
    """Scalars and plain lists inline; objects one key per line; lists of objects one item per line."""
    pad, inner_pad = "    " * level, "    " * (level + 1)
    if isinstance(value, dict):
        inner = ",\n".join(f"{inner_pad}{json.dumps(k, ensure_ascii=False)}: {_format(v, level + 1)}"
                           for k, v in value.items())
        return "{\n" + inner + ("\n" if inner else "") + pad + "}"
    if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
        items = ",\n".join(inner_pad + json.dumps(v, ensure_ascii=False).replace("{", "{ ", 1)[:-1] + " }"
                           for v in value)
        return "[\n" + items + "\n" + pad + "]"
    return json.dumps(value, ensure_ascii=False)


def update_settings(path, updates):
    """Set top-level keys, keeping the rest of the file exactly as it is."""
    with open(path, "r", encoding="utf-8-sig") as f:
        text = f.read()
    new = text
    for key, value in updates.items():
        m = re.search(r'\n    ' + re.escape(json.dumps(key)) + r'\s*:\s*', new)
        end = _value_span(new, m.end()) if m else None
        if m and end:
            new = new[:m.end()] + _format(value) + new[end:]
        else:                                     # missing: add it right after the opening brace
            new = new.replace("{\n", "{\n    " + json.dumps(key) + ": " + _format(value) + ",\n", 1)
    try:
        data = json.loads(new)
        ok = all(data.get(k) == v for k, v in updates.items())
    except ValueError:
        ok = False
    if not ok:                                    # unusual layout: rewrite the whole file
        data = json.loads(text)
        data.update(updates)
        new = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)
