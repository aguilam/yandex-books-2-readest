import zipfile, re
import lxml.etree as et
from io import BytesIO


def escape_cfi(s):
    return re.sub(r"[\^[\](),;=]", lambda m: "^" + m.group(0), s)


def tokenizer(cfi):
    tokens = []
    state = None
    escape = False
    value = ""
    chars = list(cfi.strip()) + [""]
    for char in chars:
        if char == "^" and not escape:
            escape = True
            continue
        escape = False
        if state == "!":
            tokens.append(["!"])
            state = None
            value = ""
        elif state == ",":
            tokens.append([","])
            state = None
            value = ""
        elif state in ("/", ":"):
            if char.isdigit():
                value += char
                continue
            tokens.append([state, int(value)])
            state = None
            value = ""
        elif state == "~":
            if char.isdigit() or char == ".":
                value += char
                continue
            tokens.append(["~", float(value)])
            state = None
            value = ""
        elif state == "@":
            if char == ":":
                tokens.append(["@", float(value)])
                state = "@"
                value = ""
                continue
            if char.isdigit() or char == ".":
                value += char
                continue
            tokens.append(["@", float(value)])
            state = None
            value = ""
        elif state == "[":
            if char == ";" and not escape:
                tokens.append(["[", value])
                state = ";"
                value = ""
            elif char == "," and not escape:
                tokens.append(["[", value])
                state = "["
                value = ""
            elif char == "]" and not escape:
                tokens.append(["[", value])
                state = None
                value = ""
            else:
                value += char
            continue
        elif state and state.startswith(";"):
            if char == "=" and not escape:
                state = ";" + value
                value = ""
            elif char == ";" and not escape:
                tokens.append([state, value])
                state = ";"
                value = ""
            elif char == "]" and not escape:
                tokens.append([state, value])
                state = None
                value = ""
            else:
                value += char
            continue
        if char in "/:!, [~@":
            state = char
            value = ""
        else:
            value += char
    return tokens


def find_tokens(tokens, x):
    return [i for i, t in enumerate(tokens) if t[0] == x]


def split_at(arr, indices):
    indices = [-1] + indices + [len(arr)]
    xs = []
    a = indices[0]
    for b in indices[1:]:
        xs.append(arr[a + 1 : b])
        a = b
    return xs


def parser(tokens):
    parts = []
    state = None
    for typ, val in tokens:
        if typ == "/":
            parts.append({"index": val})
        else:
            last = parts[-1]
            if typ == ":":
                last["offset"] = val
            elif typ == "~":
                last["temporal"] = val
            elif typ == "@":
                last["spatial"] = (last.get("spatial", [])) + [val]
            elif typ == ";s":
                last["side"] = val
            elif typ == "[":
                if state == "/":
                    last["id"] = val
                else:
                    last["text"] = last.get("text", []) + [val]
        state = typ
    return parts


def parser_indir(tokens):
    splits = split_at(tokens, find_tokens(tokens, "!"))
    return [parser(s) for s in splits if s]


def parse(cfi):
    tokens = tokenizer(cfi)
    commas = find_tokens(tokens, ",")
    if not commas:
        return parser_indir(tokens)
    parts = split_at(tokens, commas)
    return {
        "parent": parser_indir(parts[0]),
        "start": parser_indir(parts[1]),
        "end": parser_indir(parts[2]),
    }


def concat_arrays(a, b):
    if not a or not b:
        return a + b
    return a[:-1] + [a[-1] + b[0]] + b[1:]


def collapse(parsed, to_end=False):
    if isinstance(parsed, str):
        parsed = parse(parsed)
    if "parent" in parsed:
        return concat_arrays(parsed["parent"], parsed["end" if to_end else "start"])
    return parsed


def build_range(from_, to_):
    if isinstance(from_, str):
        from_ = parse(from_)
    if isinstance(to_, str):
        to_ = parse(to_)
    from_ = collapse(from_)
    to_ = collapse(to_)
    local_from = from_[-1]
    local_to = to_[-1]
    local_parent = []
    push_to_parent = True
    max_len = max(len(local_from), len(local_to))
    local_start = []
    local_end = []
    for i in range(max_len):
        a = local_from[i] if i < len(local_from) else None
        b = local_to[i] if i < len(local_to) else None
        if (
            push_to_parent
            and a
            and b
            and a["index"] == b["index"]
            and "offset" not in a
            and "offset" not in b
        ):
            local_parent.append(a)
        else:
            push_to_parent = False
            if a:
                local_start.append(a)
            if b:
                local_end.append(b)
    parent = from_[:-1] + [local_parent]
    return {"parent": parent, "start": [local_start], "end": [local_end]}


def part_to_string(part):
    param = ";s=" + part["side"] if "side" in part else ""
    s = f"/{part['index']}"
    id_ = escape_cfi(part["id"]) if "id" in part else ""
    text = ",".join(escape_cfi(t) for t in part["text"]) if "text" in part else ""
    if id_ or text or param:
        content = id_ if id_ else "" + text if text else ""
        s += f"[{content + param}]"
    if "offset" in part and part["index"] % 2 == 1:
        s += f":{part['offset']}"
    if "temporal" in part:
        s += f"~{part['temporal']}"
    if "spatial" in part:
        s += f"@{':'.join(map(str, part['spatial']))}"
    return s


def to_inner_string(parsed):
    if "parent" in parsed:
        return ",".join(to_inner_string(parsed[k]) for k in ["parent", "start", "end"])
    return "!".join("".join(part_to_string(p) for p in ps) for ps in parsed)


class TextNode:
    def __init__(self, value, parent):
        self.nodeValue = value
        self.parentNode = parent
        self.nodeType = 3


def is_text_node(n):
    return isinstance(n, TextNode)


def is_element_node(n):
    return isinstance(n, et.Element)


def get_child_nodes(node):
    nodes = []
    if node.text:
        nodes.append(TextNode(node.text, node))
    for child in node:
        nodes.append(child)
        if child.tail:
            nodes.append(TextNode(child.tail, node))
    return [n for n in nodes if is_text_node(n) or is_element_node(n)]


def index_child_nodes(node):
    nodes = get_child_nodes(node)
    arr = []
    for n in nodes:
        if not arr:
            arr.append(n)
            continue
        last = arr[-1]
        if is_text_node(n):
            if isinstance(last, list):
                last.append(n)
            elif is_text_node(last):
                arr[-1] = [last, n]
            else:
                arr.append(n)
        else:
            if is_element_node(last):
                arr.append(None)
            arr.append(n)
    if arr and is_element_node(arr[0]):
        arr.insert(0, "first")
    if arr and is_element_node(arr[-1]):
        arr.append("last")
    arr.insert(0, "before")
    arr.append("after")
    return arr


def parts_to_node(root, parts):
    node = root
    for part in parts:
        if "id" in part:
            els = root.xpath(f"//*[@id='{part['id']}']")
            el = els[0] if els else None
            if el is not None:
                return {"node": el, "offset": part.get("offset", 0)}
        index = part["index"]
        indexed = index_child_nodes(node)
        if index >= len(indexed):
            index = len(indexed) - 1
        new_node = indexed[index]
        if new_node == "first":
            return {"node": node, "offset": 0}
        if new_node == "last":
            total_length = sum(
                len(n.nodeValue) for n in get_child_nodes(node) if is_text_node(n)
            )
            return {"node": node, "offset": total_length}
        if new_node == "before":
            return {"node": node, "before": True}
        if new_node == "after":
            total_length = sum(
                len(n.nodeValue) for n in get_child_nodes(node) if is_text_node(n)
            )
            return {"node": node, "offset": total_length}
        if new_node is None:
            continue
        node = new_node if not isinstance(new_node, list) else new_node
    offset = parts[-1].get("offset", 0) if parts and "offset" in parts[-1] else 0
    if not isinstance(node, list):
        return {"node": node, "offset": offset}
    sum_off = 0
    for n in node:
        len_n = len(n.nodeValue)
        if sum_off + len_n >= offset:
            return {"node": n, "offset": offset - sum_off}
        sum_off += len_n
    if node:
        return {"node": node[-1], "offset": len(node[-1].nodeValue)}
    else:
        return {"node": root, "offset": 0}


def node_to_parts(node, offset=None, root=None):
    if root is None:
        if is_text_node(node):
            current = node.parentNode
        else:
            current = node
        while current.getparent() is not None:
            current = current.getparent()
        root = current
    if is_text_node(node):
        parent = node.parentNode
    else:
        parent = node.getparent()
    id_ = node.get("id") if is_element_node(node) else None
    indexed = index_child_nodes(parent)
    index = next(
        (
            i
            for i, x in enumerate(indexed)
            if x == node or (isinstance(x, list) and node in x)
        ),
        1,
    )

    chunk = indexed[index] if index != -1 else None
    if isinstance(chunk, list) and offset is not None:
        sum_off = 0
        for x in chunk:
            if x == node:
                offset = sum_off + offset
                break
            sum_off += len(x.nodeValue)
    part = {"index": index}
    if id_:
        part["id"] = id_
    if offset is not None:
        part["offset"] = offset
    if parent is not None and parent is not root:
        return node_to_parts(parent, None, root) + [part]
    return [part]


def get_chapter_html(epub_file, spine_index):
    with zipfile.ZipFile(epub_file) as z:
        container = et.parse(BytesIO(z.read("META-INF/container.xml")))
        opf_path = container.xpath("//@full-path")[0]
        opf = et.parse(BytesIO(z.read(opf_path)))
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        itemrefs = opf.xpath("//opf:spine/opf:itemref", namespaces=ns)
        if spine_index >= len(itemrefs):
            raise ValueError("Invalid spine index")
        idref = itemrefs[spine_index].get("idref")
        hrefs = opf.xpath(
            f'//opf:manifest/opf:item[@id="{idref}"]/@href', namespaces=ns
        )
        if not hrefs:
            raise ValueError("Item not found")
        href = hrefs[0]
        opf_dir = "/".join(opf_path.split("/")[:-1]) + "/" if "/" in opf_path else ""
        html_path = opf_dir + href
        parser = et.HTMLParser()
        return et.parse(BytesIO(z.read(html_path)), parser)


def epub_cfi_converter(epub_file, old_cfi: str) -> str:
    if old_cfi.startswith("epubcfi(") and old_cfi.endswith(")"):
        inner_cfi = old_cfi[len("epubcfi(") : -1]
    else:
        inner_cfi = old_cfi

    try:
        parsed = parse(inner_cfi)
        spine_index = parsed["parent"][-1][-1]["index"] // 2 - 1
        root = get_chapter_html(epub_file, spine_index).getroot()

        start_parts = parsed["start"][0][1:]
        end_parts = parsed["end"][0][1:]

        start = parts_to_node(root, start_parts)
        end = parts_to_node(root, end_parts)

        new_start_parts = node_to_parts(start["node"], start.get("offset"), root=root)
        new_end_parts = node_to_parts(end["node"], end.get("offset"), root=root)

        for p in new_start_parts + new_end_parts:
            if p["index"] < 1:
                p["index"] = 1

        has_id = any("id" in p for p in new_start_parts + new_end_parts)
        if not has_id:
            return f"epubcfi({inner_cfi})"

        local_parsed = build_range([new_start_parts], [new_end_parts])
        full_parent = parsed["parent"] + local_parsed["parent"]
        full_parsed = {
            "parent": full_parent,
            "start": local_parsed["start"],
            "end": local_parsed["end"],
        }
        new_inner = to_inner_string(full_parsed)
        return f"epubcfi({new_inner})"

    except Exception:
        return f"epubcfi({inner_cfi})"
