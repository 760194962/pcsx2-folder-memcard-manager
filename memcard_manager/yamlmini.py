"""一个够用的迷你 YAML 解析器。

只处理 PCSX2 写入 ``_pcsx2_index`` 的 "映射套映射" 结构，支持
block 风格和 flow 风格（``{a: 1, b: {c: 2}}``），键可以带引号。
"""


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def _convert_scalar(s):
    s = _unquote(s)
    try:
        return int(s)
    except ValueError:
        return s


class _Flow:
    """解析 {a: 1, b: {c: 2}} 这种 flow 映射。"""

    def __init__(self, text):
        self.t = text
        self.i = 0

    def _ws(self):
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def _token(self, stops):
        self._ws()
        if self.i < len(self.t) and self.t[self.i] in ("'", '"'):
            q = self.t[self.i]
            j = self.t.index(q, self.i + 1)
            tok = self.t[self.i + 1:j]
            self.i = j + 1
            return tok, True
        j = self.i
        while j < len(self.t) and self.t[j] not in stops:
            j += 1
        tok = self.t[self.i:j].strip()
        self.i = j
        return tok, False

    def parse_map(self):
        self._ws()
        assert self.t[self.i] == "{"
        self.i += 1
        out = {}
        while True:
            self._ws()
            if self.i >= len(self.t):
                break
            if self.t[self.i] == "}":
                self.i += 1
                break
            if self.t[self.i] == ",":
                self.i += 1
                continue
            key, _ = self._token(":,}")
            self._ws()
            if self.i < len(self.t) and self.t[self.i] == ":":
                self.i += 1
            self._ws()
            if self.i < len(self.t) and self.t[self.i] == "{":
                out[key] = self.parse_map()
            else:
                val, quoted = self._token(",}")
                out[key] = val if quoted else _convert_scalar(val)
        return out


def _split_key_value(line):
    """把 'key: value' 拆开；key 可能带引号。返回 (key, value_str)。"""
    line = line.strip()
    if line and line[0] in ("'", '"'):
        q = line[0]
        j = line.index(q, 1)
        key = line[1:j]
        rest = line[j + 1:].lstrip()
        if rest.startswith(":"):
            rest = rest[1:]
        return key, rest.strip()
    pos = line.find(": ")
    if pos == -1:
        if line.endswith(":"):
            return line[:-1], ""
        return line, ""
    return line[:pos], line[pos + 2:].strip()


def parse_index(path):
    """读取 ``_pcsx2_index``，返回 {名字: {order, timeCreated, timeModified}}。

    文件不存在或内容无法识别时返回 {}（调用方会退回到文件系统时间）。
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {}

    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        try:
            return _Flow(stripped).parse_map()
        except Exception:
            return {}

    result = {}
    current = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or raw.strip() == "---":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        try:
            key, value = _split_key_value(raw)
        except ValueError:
            continue
        if indent == 0:
            if value.startswith("{"):
                try:
                    result[key] = _Flow(value).parse_map()
                except Exception:
                    result[key] = {}
                current = None
            elif value == "":
                result[key] = {}
                current = result[key]
            else:
                result[key] = _convert_scalar(value)
                current = None
        elif current is not None:
            current[key] = _convert_scalar(value)
    return result
