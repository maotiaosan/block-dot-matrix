#!/usr/bin/env python3
import datetime
import html
import json
import os
import re
import sys

GRID_MODES = {"off": "无", "grid": "方格", "dots": "点阵"}

# 标准档沿用 Thinkly canvas-modes.css 的浓度；加深档给弱视用户
STRENGTHS = {
    "normal": {"label": "标准", "dot_alpha": 0.16, "dot_radius": 1.0, "line_alpha": 0.07},
    "strong": {"label": "加深", "dot_alpha": 0.34, "dot_radius": 1.4, "line_alpha": 0.14},
}

FONT_PX = 17
LINE_HEIGHT = 1.75
STEP_PX = round(FONT_PX * LINE_HEIGHT)  # 网格步距 = 字号 × 行高，文字每行落在格子上
INK_RGB = "31, 35, 40"

DEFAULT_CONFIG = {"grid_mode": "dots", "grid_strength": "normal"}


def now_hms():
    return datetime.datetime.now().strftime("%H:%M:%S")


def sanitize_filename(name):
    stem = os.path.splitext(os.path.basename(name or "note"))[0]
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "-", stem).strip(" .-")
    return cleaned or "note"


def clean_inline_markdown(line):
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", line)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"(\*\*|__)", "", s)
    return s.strip()


def parse_markdown_blocks(content):
    blocks = []
    in_code = False
    for raw in (content or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            blocks.append(("code", 0, line))
            continue
        if not line.strip():
            continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            blocks.append(("hr", 0, ""))
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            blocks.append(("heading", len(m.group(1)), clean_inline_markdown(m.group(2))))
            continue
        m = re.match(r"^>\s?(.*)$", line)
        if m:
            blocks.append(("quote", 0, clean_inline_markdown(m.group(1))))
            continue
        m = re.match(r"^\s*(?:[-*+]|(\d+)\.)\s+(.*)$", line)
        if m:
            prefix = f"{m.group(1)}. " if m.group(1) else "• "
            blocks.append(("list", 0, prefix + clean_inline_markdown(m.group(2))))
            continue
        text = clean_inline_markdown(line)
        if text:
            blocks.append(("paragraph", 0, text))
    return blocks


def pattern_css(mode, strength):
    """点阵/方格只铺在内缩区域里，用 round 整数平铺：四边留白对称，不会贴边或被裁半。"""
    s = STRENGTHS[strength]
    step = STEP_PX
    if mode == "dots":
        r = s["dot_radius"]
        layer = (
            f"radial-gradient(circle at 50% 50%, rgba({INK_RGB}, {s['dot_alpha']}) {r}px, "
            f"transparent {r + 0.5}px) 0 0 / {step}px {step}px round"
        )
        return layer, round(step / 2)
    if mode == "grid":
        c = f"rgba({INK_RGB}, {s['line_alpha']})"
        layer = ", ".join([
            f"linear-gradient(to left, {c} 1px, transparent 1px) 0 0 / 100% 100% no-repeat",
            f"linear-gradient(to top, {c} 1px, transparent 1px) 0 0 / 100% 100% no-repeat",
            f"linear-gradient(to bottom, {c} 1px, transparent 1px) 0 0 / {step}px {step}px round",
            f"linear-gradient(to right, {c} 1px, transparent 1px) 0 0 / {step}px {step}px round",
        ])
        return layer, step
    return "none", 0


def build_reader_html(note_path, blocks, cfg):
    mode = cfg["grid_mode"]
    layer, inset = pattern_css(mode, cfg["grid_strength"])
    step = STEP_PX

    rows = []
    for kind, level, text in blocks:
        t = html.escape(text)
        if kind == "hr":
            rows.append("<hr>")
        elif kind == "heading":
            lvl = min(max(level, 1), 3)
            rows.append(f"<h{lvl}>{t}</h{lvl}>")
        elif kind == "quote":
            rows.append(f"<blockquote>{t}</blockquote>")
        elif kind == "code":
            rows.append(f"<pre>{t or ' '}</pre>")
        else:
            rows.append(f"<p>{t}</p>")
    if not rows:
        rows.append("<p>这篇笔记还没有内容。</p>")

    title = html.escape(sanitize_filename(note_path) if note_path else "笔记")
    pattern_div = "" if mode == "off" else '<div class="pattern" aria-hidden="true"></div>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: #ffffff; }}
body {{
  color: #2b3038;
  font-family: Inter, -apple-system, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  font-size: {FONT_PX}px;
  line-height: {step}px;
}}
main {{ position: relative; min-height: 100vh; padding: {step * 2}px 48px {step * 3}px; }}
.pattern {{ position: absolute; inset: {inset}px; pointer-events: none; background: {layer}; }}
article {{ position: relative; max-width: 720px; margin: 0 auto; }}
h1, h2, h3, p, blockquote, pre {{ margin: 0; }}
h1 {{ font-size: {round(FONT_PX * 1.75)}px; line-height: {step * 2}px; font-weight: 700; color: #1f2328; }}
h2 {{ margin-top: {step}px; font-size: {round(FONT_PX * 1.25)}px; line-height: {step}px; font-weight: 650; color: #1f2328; }}
h3 {{ margin-top: {step}px; font-size: {FONT_PX}px; line-height: {step}px; font-weight: 650; color: #1f2328; }}
blockquote {{ padding-left: 16px; border-left: 2px solid #c9ccd2; color: #4a505a; }}
pre {{ font-family: "JetBrains Mono", Menlo, ui-monospace, monospace; font-size: 15px; white-space: pre-wrap; }}
hr {{ border: none; height: {step}px; margin: 0; background: linear-gradient(#e6e7ea, #e6e7ea) center / 100% 1px no-repeat; }}
@media (max-width: 640px) {{ main {{ padding-left: 20px; padding-right: 20px; }} }}
</style>
</head>
<body>
<main>
{pattern_div}
<article>
{chr(10).join(rows)}
</article>
</main>
</body>
</html>
"""


class HostBridge:
    def __init__(self):
        self._seq = 1000

    def send(self, obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def call_host(self, method, params=None):
        self._seq += 1
        req_id = f"p-{self._seq}"
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        while True:
            line = sys.stdin.readline()
            if not line:
                raise RuntimeError("stdin closed while awaiting host response")
            msg = json.loads(line)
            if str(msg.get("id")) == req_id:
                if msg.get("error"):
                    raise RuntimeError(msg["error"].get("message", "host error"))
                return msg.get("result", {})

    def serve(self, handler):
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            req = json.loads(line)
            method = req.get("method")
            req_id = req.get("id")
            try:
                result = handler(self, method, req.get("params") or {})
                self.send({"jsonrpc": "2.0", "id": req_id, "result": result})
                if method == "plugin.shutdown":
                    break
            except Exception as exc:
                self.send({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": str(exc)}})


class CanvasDotsPlugin:
    def __init__(self):
        self.downloads_dir = os.path.expanduser("~/Downloads")
        self.last_status = ""

    def normalize(self, cfg):
        out = dict(DEFAULT_CONFIG)
        if cfg.get("grid_mode") in GRID_MODES:
            out["grid_mode"] = cfg["grid_mode"]
        if cfg.get("grid_strength") in STRENGTHS:
            out["grid_strength"] = cfg["grid_strength"]
        return out

    def load_config(self, bridge):
        try:
            res = bridge.call_host("host.storage.get", {"key": "config"})
            if res.get("found") and isinstance(res.get("value"), dict):
                return self.normalize(res["value"])
        except Exception:
            pass
        return dict(DEFAULT_CONFIG)

    def save_config(self, bridge, cfg):
        try:
            bridge.call_host("host.storage.set", {"key": "config", "value": cfg})
        except Exception:
            pass

    def merge_values(self, cfg, values):
        if not isinstance(values, dict):
            return cfg
        merged = dict(cfg)
        for key in ("grid_mode", "grid_strength"):
            if isinstance(values.get(key), str):
                merged[key] = values[key]
        return self.normalize(merged)

    def target_note(self, bridge):
        try:
            active = (bridge.call_host("host.notes.active", {}).get("path") or "").strip()
            if active:
                return active
        except Exception:
            pass
        try:
            notes = bridge.call_host("host.notes.list", {}).get("notes", [])
            paths = [n.get("path") for n in notes if n.get("path")]
            return paths[0] if paths else ""
        except Exception:
            return ""

    def read_note(self, bridge, path):
        if not path:
            return ""
        try:
            return bridge.call_host("host.notes.read", {"path": path}).get("content") or ""
        except Exception:
            return ""

    def build_page(self, cfg):
        return {
            "title": "画布点阵",
            "status": self.last_status,
            "header_actions": [
                {"id": "open_reader", "label": "打开点阵阅读页", "variant": "primary"},
            ],
            "cards": [
                {
                    "id": "canvas-card",
                    "title": "画布",
                    "items": [
                        {
                            "kind": "segmented",
                            "id": "grid_mode",
                            "label": "编辑器网格",
                            "value": cfg["grid_mode"],
                            "options": [{"value": k, "label": v} for k, v in GRID_MODES.items()],
                        },
                        {
                            "kind": "segmented",
                            "id": "grid_strength",
                            "label": "网格深浅",
                            "value": cfg["grid_strength"],
                            "options": [{"value": k, "label": v["label"]} for k, v in STRENGTHS.items()],
                        },
                    ],
                }
            ],
        }

    def handle(self, bridge, method, params):
        if method == "plugin.initialize":
            dl = (params.get("downloads_dir") or "").strip()
            if dl:
                self.downloads_dir = dl
            return {"ready": True}

        if method == "plugin.render":
            cfg = self.merge_values(self.load_config(bridge), params.get("values"))
            return {"page": self.build_page(cfg)}

        if method == "plugin.action":
            action_id = (params.get("action_id") or "").strip()
            cfg = self.merge_values(self.load_config(bridge), params.get("values"))
            self.save_config(bridge, cfg)

            if action_id == "open_reader":
                path = self.target_note(bridge)
                blocks = parse_markdown_blocks(self.read_note(bridge, path))
                os.makedirs(self.downloads_dir, exist_ok=True)
                out_path = os.path.join(self.downloads_dir, f"{sanitize_filename(path or 'block-note')}-点阵阅读.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(build_reader_html(path, blocks, cfg))
                self.last_status = f"上次打开 {now_hms()}"
                return {"values": cfg, "page": self.build_page(cfg), "status": self.last_status, "open_path": out_path}

            return {"values": cfg, "page": self.build_page(cfg), "status": f"未知操作：{action_id}"}

        if method == "plugin.shutdown":
            return {"ok": True}

        raise RuntimeError(f"unsupported method: {method}")


if __name__ == "__main__":
    HostBridge().serve(CanvasDotsPlugin().handle)
