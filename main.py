#!/usr/bin/env python3
import datetime
import html
import json
import os
import re
import sys

MARKER_START = "<!-- block-dot-matrix:start -->"
MARKER_END = "<!-- block-dot-matrix:end -->"

# Standard Grade-1 6-dot Braille Unicode characters (U+2800..U+283F)
BRAILLE_ALPHA = {
    "a": "\u2801", "b": "\u2803", "c": "\u2809", "d": "\u2819", "e": "\u2811",
    "f": "\u280b", "g": "\u281b", "h": "\u2813", "i": "\u280a", "j": "\u281a",
    "k": "\u2805", "l": "\u2807", "m": "\u280d", "n": "\u281d", "o": "\u2815",
    "p": "\u280f", "q": "\u281f", "r": "\u2817", "s": "\u280e", "t": "\u281e",
    "u": "\u2825", "v": "\u2827", "w": "\u283a", "x": "\u282d", "y": "\u283d",
    "z": "\u2835",
}

BRAILLE_DIGITS = {
    "1": "\u2801", "2": "\u2803", "3": "\u2809", "4": "\u2819", "5": "\u2811",
    "6": "\u280b", "7": "\u281b", "8": "\u2813", "9": "\u280a", "0": "\u281a",
}

BRAILLE_PUNCT = {
    ",": "\u2802", ";": "\u2806", ":": "\u2812", ".": "\u2832", "!": "\u2816",
    "?": "\u2826", "-": "\u2824", "(": "\u2836", ")": "\u2836", "/": "\u280c",
    "'": "\u2804", '"': "\u2826",
    "，": "\u2802", "。": "\u2832", "！": "\u2816", "？": "\u2826",
    "：": "\u2812", "；": "\u2806", "、": "\u2802", "（": "\u2836", "）": "\u2836",
    "「": "\u2826", "」": "\u2834", "《": "\u2826", "》": "\u2834",
}

CAPITAL_SIGN = "\u2820"
NUMBER_SIGN = "\u283c"

PALETTES = {
    "amber_dark": {
        "name": "暗夜金黄",
        "contrast": "AAA 15.8:1",
        "preview_palette": "ink",
        "bg": "#0b0d12",
        "panel": "#131722",
        "box": "#090b10",
        "fg": "#fff9e6",
        "sub": "#d7deea",
        "accent": "#ffe066",
        "accent_ink": "#0b0d12",
        "border": "rgba(255, 224, 102, 0.44)",
        "focus_bg": "rgba(255, 224, 102, 0.14)",
        "dot": "rgba(255, 224, 102, 0.25)",
    },
    "mono_dark": {
        "name": "纯黑亮白",
        "contrast": "AAA 21.0:1",
        "preview_palette": "ink",
        "bg": "#000000",
        "panel": "#111111",
        "box": "#080808",
        "fg": "#ffffff",
        "sub": "#e2e8f0",
        "accent": "#93c5fd",
        "accent_ink": "#000000",
        "border": "rgba(255, 255, 255, 0.48)",
        "focus_bg": "rgba(147, 197, 253, 0.16)",
        "dot": "rgba(255, 255, 255, 0.28)",
    },
    "navy_light": {
        "name": "深海暖白",
        "contrast": "AAA 14.2:1",
        "preview_palette": "paper",
        "bg": "#f7f9fc",
        "panel": "#ffffff",
        "box": "#edf2fa",
        "fg": "#0b1324",
        "sub": "#2b3a55",
        "accent": "#1d4ed8",
        "accent_ink": "#ffffff",
        "border": "rgba(29, 78, 216, 0.38)",
        "focus_bg": "rgba(29, 78, 216, 0.10)",
        "dot": "rgba(15, 39, 86, 0.22)",
    },
}

DENSITY_PX = {"loose": 24, "medium": 18, "dense": 14}
FONT_SCALE_PX = {"normal": 22, "large": 26, "xlarge": 32}

DEFAULT_CONFIG = {
    "target_note": "__active__",
    "mode": "hybrid",
    "palette": "amber_dark",
    "dot_density": "medium",
    "font_scale": "large",
    "auto_sync_note": False,
    "speech_assist": True,
}


def now_hms():
    return datetime.datetime.now().strftime("%H:%M:%S")


def sanitize_filename(name):
    stem = os.path.splitext(os.path.basename(name or "note"))[0]
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "-", stem).strip(" .-")
    return cleaned or "note"


def strip_embedded_block(content):
    pattern = re.compile(
        r"\n*" + re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END) + r"\n*",
        re.DOTALL,
    )
    return pattern.sub("\n", content or "").rstrip()


def cjk_to_braille_cells(ch):
    """Deterministic 2-cell 6-dot Braille encoding for CJK characters so every glyph maps stably."""
    cp = ord(ch)
    low = (cp & 0x3F) or 0x01
    high = ((cp >> 6) & 0x3F) or 0x02
    return chr(0x2800 + high) + chr(0x2800 + low)


def text_to_braille(text):
    out = []
    in_number = False
    for ch in text:
        if ch.isspace():
            in_number = False
            out.append(" ")
            continue
        if "0" <= ch <= "9":
            if not in_number:
                out.append(NUMBER_SIGN)
                in_number = True
            out.append(BRAILLE_DIGITS[ch])
            continue
        in_number = False
        if "A" <= ch <= "Z":
            out.append(CAPITAL_SIGN + BRAILLE_ALPHA[ch.lower()])
        elif "a" <= ch <= "z":
            out.append(BRAILLE_ALPHA[ch])
        elif ch in BRAILLE_PUNCT:
            out.append(BRAILLE_PUNCT[ch])
        elif "\u4e00" <= ch <= "\u9fff":
            out.append(cjk_to_braille_cells(ch))
        elif 0x2800 <= ord(ch) <= 0x28FF:
            out.append(ch)
        else:
            out.append(chr(0x2800 + ((ord(ch) & 0x3E) | 0x01)))
    return re.sub(r" {2,}", " ", "".join(out)).strip()


def clean_inline_markdown(line):
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[\1]", line)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"(\*\*|__|\*|_)", "", s)
    return s.strip()


def parse_markdown_blocks(content):
    cleaned = strip_embedded_block(content)
    blocks = []
    in_code = False
    for raw in cleaned.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not line.strip():
            continue
        if in_code:
            text = line.strip()
            braille = "\u2828 " + text_to_braille(text)
            blocks.append({"tag": "代码", "level": 0, "text": text, "braille": braille})
            continue
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", line.strip()):
            blocks.append({
                "tag": "分隔",
                "level": 0,
                "text": "----------------",
                "braille": "\u283f\u283f\u283f\u283f\u283f\u283f",
            })
            continue
        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_head:
            lvl = len(m_head.group(1))
            text = clean_inline_markdown(m_head.group(2))
            prefix = "\u283f" * min(lvl, 3)
            blocks.append({
                "tag": f"H{lvl}",
                "level": lvl,
                "text": text,
                "braille": f"{prefix} {text_to_braille(text)}".strip(),
            })
            continue
        m_quote = re.match(r"^>\s?(.*)$", line)
        if m_quote:
            text = clean_inline_markdown(m_quote.group(1))
            blocks.append({
                "tag": "引用",
                "level": 0,
                "text": text,
                "braille": f"\u2807 {text_to_braille(text)}".strip(),
            })
            continue
        m_list = re.match(r"^[-*+]\s+(.*)$|^\d+\.\s+(.*)$", line.strip())
        if m_list:
            text = clean_inline_markdown(m_list.group(1) or m_list.group(2) or "")
            blocks.append({
                "tag": "列表",
                "level": 0,
                "text": text,
                "braille": f"\u2815 {text_to_braille(text)}".strip(),
            })
            continue
        text = clean_inline_markdown(line)
        if text:
            blocks.append({
                "tag": "正文",
                "level": 0,
                "text": text,
                "braille": text_to_braille(text),
            })
    return blocks


def count_braille_cells(blocks):
    return sum(1 for b in blocks for ch in b["braille"] if 0x2800 <= ord(ch) <= 0x28FF)


def build_embedded_braille_section(blocks, mode):
    lines = [
        MARKER_START,
        "## 无障碍盲文点阵速览",
        "",
    ]
    for idx, blk in enumerate(blocks[:60], start=1):
        prefix = f"{idx:02d} [{blk['tag']}]"
        if mode == "braille":
            lines.append(f"- `{prefix}` {blk['braille']}")
        else:
            lines.append(f"- `{prefix}` {blk['text']}")
            lines.append(f"  `{blk['braille']}`")
    lines.extend(["", MARKER_END])
    return "\n".join(lines)


def build_reader_html(note_path, blocks, cfg):
    pal_key = cfg.get("palette", "amber_dark")
    pal = PALETTES.get(pal_key, PALETTES["amber_dark"])
    grid_px = DENSITY_PX.get(cfg.get("dot_density", "medium"), 18)
    font_px = FONT_SCALE_PX.get(cfg.get("font_scale", "large"), 26)
    mode = cfg.get("mode", "hybrid")
    speech = bool(cfg.get("speech_assist", True))
    show_braille = mode != "low_vision"

    title_esc = html.escape(note_path or "未命名笔记")
    rows_html = []
    for idx, blk in enumerate(blocks, start=1):
        txt_esc = html.escape(blk["text"])
        br_esc = html.escape(blk["braille"])
        tag_esc = html.escape(blk["tag"])
        is_heading = blk["level"] > 0
        heading_cls = " is-heading" if is_heading else ""
        braille_html = (
            f'<div class="braille-line" aria-label="盲文点阵">{br_esc}</div>'
            if show_braille
            else ""
        )
        rows_html.append(
            f'<article class="block-row{heading_cls}" tabindex="0" data-index="{idx}" '
            f'aria-label="第 {idx} 段 {tag_esc} {txt_esc}">'
            f'<div class="anchor-col" aria-hidden="true">'
            f'<span class="line-num">{idx:02d}</span>'
            f'<span class="anchor-dot"></span>'
            f'<span class="line-tag">{tag_esc}</span>'
            f'</div>'
            f'<div class="content-col">'
            f'<div class="text-line">{txt_esc}</div>'
            f'{braille_html}'
            f'</div>'
            f'</article>'
        )

    if not rows_html:
        rows_html.append(
            '<article class="block-row" tabindex="0">'
            '<div class="anchor-col"><span class="line-num">01</span><span class="anchor-dot"></span><span class="line-tag">提示</span></div>'
            '<div class="content-col"><div class="text-line">当前笔记暂无正文内容。</div></div>'
            '</article>'
        )

    speech_btn = (
        '<button type="button" id="btn-speak" class="ctrl-btn">朗读当前段</button>'
        if speech
        else ""
    )

    themes_json = json.dumps(PALETTES, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc} · 点阵无障碍阅读</title>
<style>
:root {{
  --bg: {pal['bg']};
  --panel: {pal['panel']};
  --box: {pal['box']};
  --fg: {pal['fg']};
  --sub: {pal['sub']};
  --accent: {pal['accent']};
  --accent-ink: {pal['accent_ink']};
  --border: {pal['border']};
  --focus-bg: {pal['focus_bg']};
  --dot: {pal['dot']};
  --grid: {grid_px}px;
  --font-size: {font_px}px;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  background-color: var(--bg);
  background-image: radial-gradient(var(--dot) 1.6px, transparent 1.6px);
  background-size: var(--grid) var(--grid);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}}
body.grid-off {{ background-image: none; }}
.skip-link {{
  position: absolute;
  left: -9999px;
  top: 8px;
  padding: 12px 18px;
  background: var(--accent);
  color: var(--accent-ink);
  font-weight: 700;
  border-radius: 8px;
}}
.skip-link:focus {{ left: 16px; z-index: 100; }}
.wrap {{
  max-width: 1060px;
  margin: 0 auto;
  padding: 24px 24px 64px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}}
.toolbar {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-radius: 12px;
  background: var(--panel);
  border: 2px solid var(--border);
}}
.title-box {{ display: flex; flex-direction: column; gap: 4px; }}
.title-box h1 {{ margin: 0; font-size: 20px; line-height: 1.3; }}
.meta-line {{ font-size: 13px; color: var(--sub); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.ctrl-btn {{
  min-height: 44px;
  padding: 0 14px;
  border-radius: 8px;
  border: 2px solid var(--border);
  background: transparent;
  color: var(--fg);
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}}
.ctrl-btn[aria-pressed="true"] {{
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}}
.ctrl-btn:focus-visible, .block-row:focus-visible {{
  outline: 3px solid var(--accent);
  outline-offset: 2px;
}}
main {{ display: flex; flex-direction: column; gap: 14px; }}
.block-row {{
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 18px 20px;
  border-radius: 12px;
  background: var(--panel);
  border: 2px solid var(--border);
  cursor: pointer;
}}
.block-row.is-active {{
  background: var(--focus-bg);
  border-color: var(--accent);
}}
.anchor-col {{
  width: 52px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
}}
.line-num {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}}
.anchor-dot {{
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: var(--accent);
}}
.line-tag {{ font-size: 12px; color: var(--sub); }}
.content-col {{
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}
.text-line {{
  font-size: var(--font-size);
  line-height: 1.7;
  font-weight: 600;
  letter-spacing: 0.04em;
  word-break: break-word;
}}
.block-row.is-heading .text-line {{
  font-size: calc(var(--font-size) * 1.28);
  font-weight: 800;
}}
.braille-line {{
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--box);
  border: 1px dashed var(--border);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(var(--font-size) * 0.85);
  letter-spacing: 0.16em;
  line-height: 1.55;
  color: var(--accent);
  word-break: break-all;
}}
@media print {{
  .toolbar {{ display: none; }}
  body {{ background: #ffffff !important; color: #000000 !important; }}
  .block-row {{ border: 1px solid #111111; background: #ffffff; break-inside: avoid; }}
  .braille-line {{ background: #f5f5f5; color: #000000; border-color: #333333; }}
}}
</style>
</head>
<body>
<a class="skip-link" href="#reader-main">跳到正文点阵内容</a>
<div class="wrap">
  <header class="toolbar" role="banner">
    <div class="title-box">
      <h1>{title_esc}</h1>
      <div class="meta-line" id="status-line">对比度 {pal['contrast']} · 步距 {grid_px}px · 字号 {font_px}px</div>
    </div>
    <div class="controls" role="toolbar" aria-label="阅读显示控制">
      <button type="button" class="ctrl-btn" data-theme="amber_dark" aria-pressed="{str(pal_key == 'amber_dark').lower()}">暗夜金黄</button>
      <button type="button" class="ctrl-btn" data-theme="mono_dark" aria-pressed="{str(pal_key == 'mono_dark').lower()}">纯黑亮白</button>
      <button type="button" class="ctrl-btn" data-theme="navy_light" aria-pressed="{str(pal_key == 'navy_light').lower()}">深海暖白</button>
      <button type="button" id="btn-dec" class="ctrl-btn" aria-label="缩小字号">A-</button>
      <button type="button" id="btn-inc" class="ctrl-btn" aria-label="放大字号">A+</button>
      <button type="button" id="btn-grid" class="ctrl-btn" aria-pressed="true">点阵网格</button>
      {speech_btn}
    </div>
  </header>
  <main id="reader-main" role="main">
    {''.join(rows_html)}
  </main>
</div>
<script>
const THEMES = {themes_json};
let currentTheme = {json.dumps(pal_key)};
let currentFont = {font_px};
let activeRow = document.querySelector('.block-row');
if (activeRow) activeRow.classList.add('is-active');

function updateMeta() {{
  const t = THEMES[currentTheme] || THEMES.amber_dark;
  const gridOn = !document.body.classList.contains('grid-off');
  document.getElementById('status-line').textContent =
    '对比度 ' + t.contrast + ' · 字号 ' + currentFont + 'px · 防串行点阵 ' + (gridOn ? '开启' : '关闭');
}}

function applyTheme(key) {{
  const t = THEMES[key];
  if (!t) return;
  currentTheme = key;
  const r = document.documentElement.style;
  r.setProperty('--bg', t.bg);
  r.setProperty('--panel', t.panel);
  r.setProperty('--box', t.box);
  r.setProperty('--fg', t.fg);
  r.setProperty('--sub', t.sub);
  r.setProperty('--accent', t.accent);
  r.setProperty('--accent-ink', t.accent_ink);
  r.setProperty('--border', t.border);
  r.setProperty('--focus-bg', t.focus_bg);
  r.setProperty('--dot', t.dot);
  document.querySelectorAll('[data-theme]').forEach(btn => {{
    btn.setAttribute('aria-pressed', btn.getAttribute('data-theme') === key ? 'true' : 'false');
  }});
  updateMeta();
}}

document.querySelectorAll('[data-theme]').forEach(btn => {{
  btn.addEventListener('click', () => applyTheme(btn.getAttribute('data-theme')));
}});
document.getElementById('btn-dec').addEventListener('click', () => {{
  currentFont = Math.max(16, currentFont - 2);
  document.documentElement.style.setProperty('--font-size', currentFont + 'px');
  updateMeta();
}});
document.getElementById('btn-inc').addEventListener('click', () => {{
  currentFont = Math.min(44, currentFont + 2);
  document.documentElement.style.setProperty('--font-size', currentFont + 'px');
  updateMeta();
}});
document.getElementById('btn-grid').addEventListener('click', (e) => {{
  document.body.classList.toggle('grid-off');
  e.currentTarget.setAttribute('aria-pressed', document.body.classList.contains('grid-off') ? 'false' : 'true');
  updateMeta();
}});
document.querySelectorAll('.block-row').forEach(row => {{
  const activate = () => {{
    document.querySelectorAll('.block-row.is-active').forEach(el => el.classList.remove('is-active'));
    row.classList.add('is-active');
    activeRow = row;
  }};
  row.addEventListener('click', activate);
  row.addEventListener('focus', activate);
}});
const speakBtn = document.getElementById('btn-speak');
if (speakBtn) {{
  speakBtn.addEventListener('click', () => {{
    if (!('speechSynthesis' in window) || !activeRow) return;
    window.speechSynthesis.cancel();
    const txt = activeRow.querySelector('.text-line')?.textContent || '';
    const u = new SpeechSynthesisUtterance(txt);
    u.lang = 'zh-CN';
    window.speechSynthesis.speak(u);
  }});
}}
</script>
</body>
</html>
"""


def build_tactile_svg(note_path, blocks):
    """Build a crisp A4-proportioned tactile Braille dot-matrix SVG with raised solid dots."""
    width = 794
    margin_x = 46
    cells_per_row = 22
    cell_w = 31
    row_h = 84
    header_h = 104

    selected_blocks = blocks[:10] if blocks else [
        {"tag": "提示", "text": "当前笔记暂无正文", "braille": text_to_braille("empty")}
    ]
    total_h = max(1123, header_h + len(selected_blocks) * row_h + 72)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" viewBox="0 0 {width} {total_h}">',
        '<rect x="0" y="0" width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_x}" y="44" font-family="sans-serif" font-size="13" font-weight="700" fill="#374151">BLOCK DOT MATRIX · A4 触觉盲文点阵图</text>',
        f'<text x="{margin_x}" y="74" font-family="sans-serif" font-size="22" font-weight="700" fill="#111827">{html.escape(note_path or "note.md")}</text>',
        f'<line x1="{margin_x}" y1="90" x2="{width - margin_x}" y2="90" stroke="#111827" stroke-width="2"/>',
    ]

    dot_offsets = [
        (0, 0),   # dot 1
        (0, 9),   # dot 2
        (0, 18),  # dot 3
        (9, 0),   # dot 4
        (9, 9),   # dot 5
        (9, 18),  # dot 6
    ]

    for row_idx, blk in enumerate(selected_blocks):
        top_y = header_h + row_idx * row_h
        caption = f"{row_idx + 1:02d} [{blk['tag']}] {blk['text'][:38]}"
        parts.append(
            f'<rect x="{margin_x}" y="{top_y}" width="{width - margin_x * 2}" height="{row_h - 12}" rx="8" fill="#fcfcfd" stroke="#cbd5e1" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{margin_x + 14}" y="{top_y + 22}" font-family="sans-serif" font-size="13" font-weight="700" fill="#111827">{html.escape(caption)}</text>'
        )
        braille_chars = [ch for ch in blk["braille"] if 0x2800 <= ord(ch) <= 0x28FF][:cells_per_row]
        for ci, ch in enumerate(braille_chars):
            bits = ord(ch) - 0x2800
            cx0 = margin_x + 18 + ci * cell_w
            cy0 = top_y + 38
            for bit_i, (dx, dy) in enumerate(dot_offsets):
                is_raised = bool(bits & (1 << bit_i))
                if is_raised:
                    parts.append(f'<circle cx="{cx0 + dx}" cy="{cy0 + dy}" r="3.1" fill="#111827"/>')
                else:
                    parts.append(f'<circle cx="{cx0 + dx}" cy="{cy0 + dy}" r="2.5" fill="#ffffff" stroke="#cbd5e1" stroke-width="1"/>')

    parts.append(
        f'<text x="{margin_x}" y="{total_h - 24}" font-family="monospace" font-size="12" fill="#475569">实心黑点 = 凸起盲文点位（1-6点） · 矢量可打印触觉稿</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


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
                if "error" in msg and msg["error"]:
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


class DotMatrixPlugin:
    def __init__(self):
        self.downloads_dir = os.path.expanduser("~/Downloads")
        self.notebook_root = ""
        self.ui_capabilities = set()
        self.last_status = ""

    def load_config(self, bridge):
        cfg = dict(DEFAULT_CONFIG)
        try:
            res = bridge.call_host("host.storage.get", {"key": "config"})
            if res.get("found") and isinstance(res.get("value"), dict):
                for k, v in res["value"].items():
                    if k in cfg:
                        cfg[k] = v
        except Exception:
            pass
        return cfg

    def save_config(self, bridge, cfg):
        try:
            bridge.call_host("host.storage.set", {"key": "config", "value": cfg})
        except Exception:
            pass

    def load_logs(self, bridge):
        try:
            res = bridge.call_host("host.storage.get", {"key": "logs"})
            if res.get("found") and isinstance(res.get("value"), list):
                return res["value"][:12]
        except Exception:
            pass
        return []

    def append_log(self, bridge, title, status):
        logs = self.load_logs(bridge)
        logs.insert(0, {"title": title, "time": now_hms(), "status": status})
        try:
            bridge.call_host("host.storage.set", {"key": "logs", "value": logs[:12]})
        except Exception:
            pass

    def merge_values(self, cfg, values):
        if not isinstance(values, dict):
            return cfg
        updated = dict(cfg)
        for key in ("target_note", "mode", "palette", "dot_density", "font_scale"):
            if key in values and isinstance(values[key], str):
                updated[key] = values[key]
        for key in ("auto_sync_note", "speech_assist"):
            if key in values and isinstance(values[key], bool):
                updated[key] = values[key]
        return updated

    def fetch_notes(self, bridge):
        notes = []
        active = ""
        try:
            res = bridge.call_host("host.notes.list", {})
            notes = [n.get("path", "") for n in res.get("notes", []) if n.get("path")]
        except Exception:
            notes = []
        try:
            res = bridge.call_host("host.notes.active", {})
            active = (res.get("path") or "").strip()
        except Exception:
            active = ""
        return notes, active

    def resolve_target_note(self, cfg, notes, active):
        chosen = cfg.get("target_note", "__active__")
        if chosen == "__active__":
            if active and (not notes or active in notes):
                return active
            return notes[0] if notes else ""
        if chosen in notes:
            return chosen
        return active or (notes[0] if notes else "")

    def read_note(self, bridge, note_path):
        if not note_path:
            return ""
        try:
            res = bridge.call_host("host.notes.read", {"path": note_path})
            return res.get("content") or ""
        except Exception:
            return ""

    def build_page(self, bridge, cfg):
        notes, active = self.fetch_notes(bridge)
        active_label = f"当前活动笔记（{active}）" if active else "当前活动笔记"
        note_options = [{"value": "__active__", "label": active_label}]
        for p in notes[:80]:
            note_options.append({"value": p, "label": p})

        valid_note_vals = {o["value"] for o in note_options}
        selected_note_val = cfg.get("target_note", "__active__")
        if selected_note_val not in valid_note_vals:
            selected_note_val = "__active__"

        target_path = self.resolve_target_note(cfg, notes, active)
        content = self.read_note(bridge, target_path)
        blocks = parse_markdown_blocks(content)
        braille_count = count_braille_cells(blocks)

        pal_key = cfg.get("palette", "amber_dark")
        if pal_key not in PALETTES:
            pal_key = "amber_dark"
        pal = PALETTES[pal_key]

        mode = cfg.get("mode", "hybrid")
        if mode not in ("hybrid", "braille", "low_vision"):
            mode = "hybrid"

        density = cfg.get("dot_density", "medium")
        if density not in DENSITY_PX:
            density = "medium"
        grid_px = DENSITY_PX[density]

        font_scale = cfg.get("font_scale", "large")
        if font_scale not in FONT_SCALE_PX:
            font_scale = "large"

        sample_blocks = blocks[:5]
        if sample_blocks:
            before_text = "\n".join(f"{i:02d} [{b['tag']}] {b['text']}" for i, b in enumerate(sample_blocks, 1))
            after_text = "\n".join(f"{i:02d} {b['braille']}" for i, b in enumerate(sample_blocks, 1))
            article_body = "\n".join(
                (f"# {b['text']}" if b["level"] == 1 else f"## {b['text']}" if b["level"] >= 2 else f"> {i:02d} · {b['text']}")
                for i, b in enumerate(sample_blocks, 1)
            )
        else:
            before_text = "01 [提示] 打开包含 Markdown 笔记的笔记本后将自动展示点阵转换对照。"
            after_text = "01 " + text_to_braille("Block Dot Matrix")
            article_body = "# 点阵大字阅读预览\n> 打开任意笔记后即可生成防串行点阵与盲文对照视图。"

        if mode == "low_vision":
            preview_obj = {
                "variant": "article",
                "palette": pal["preview_palette"],
                "title": f"防串行点阵预览 · {target_path or '示例笔记'}",
                "badge": f"{pal['name']} · {pal['contrast']}",
                "subtitle": f"点阵步距 {grid_px}px · 字号 {FONT_SCALE_PX[font_scale]}px",
                "body": article_body,
            }
        else:
            preview_obj = {
                "variant": "diff",
                "palette": pal["preview_palette"],
                "title": f"盲文点阵对照预览 · {target_path or '示例笔记'}",
                "badge": f"{braille_count} 格盲文 · {pal['contrast']}",
                "subtitle": f"{sanitize_filename(target_path)}-点阵阅读.html",
                "before": before_text,
                "after": after_text,
            }

        dl_name = os.path.basename(self.downloads_dir.rstrip(os.sep)) or "Downloads"
        dl_row = {"label": "导出目录", "value": dl_name}
        if "kv_tooltip" in self.ui_capabilities:
            dl_row["tooltip"] = self.downloads_dir

        note_row = {"label": "当前目标笔记", "value": target_path or "未打开笔记本"}
        if "kv_tooltip" in self.ui_capabilities and self.notebook_root and target_path:
            note_row["tooltip"] = os.path.join(self.notebook_root, target_path)

        logs = self.load_logs(bridge)

        return {
            "title": "点阵阅读",
            "status": self.last_status,
            "header_actions": [
                {"id": "open_reader", "label": "打开点阵阅读页", "variant": "primary"},
                {"id": "export_tactile_svg", "label": "导出触觉 SVG", "variant": "secondary"},
            ],
            "cards": [
                {
                    "id": "config-card",
                    "title": "点阵与无障碍设置",
                    "items": [
                        {
                            "kind": "select",
                            "id": "target_note",
                            "label": "目标笔记",
                            "value": selected_note_val,
                            "options": note_options,
                        },
                        {
                            "kind": "segmented",
                            "id": "mode",
                            "label": "输出模式",
                            "value": mode,
                            "options": [
                                {"value": "hybrid", "label": "综合点阵"},
                                {"value": "braille", "label": "纯盲文"},
                                {"value": "low_vision", "label": "防串行大字"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "palette",
                            "label": "高对比度配色",
                            "value": pal_key,
                            "options": [
                                {"value": "amber_dark", "label": "暗夜金黄"},
                                {"value": "mono_dark", "label": "纯黑亮白"},
                                {"value": "navy_light", "label": "深海暖白"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "dot_density",
                            "label": "防串行点阵步距",
                            "value": density,
                            "options": [
                                {"value": "loose", "label": "疏 24px"},
                                {"value": "medium", "label": "中 18px"},
                                {"value": "dense", "label": "密 14px"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "font_scale",
                            "label": "阅读页字号",
                            "value": font_scale,
                            "options": [
                                {"value": "normal", "label": "22px"},
                                {"value": "large", "label": "26px"},
                                {"value": "xlarge", "label": "32px"},
                            ],
                        },
                        {
                            "kind": "switch",
                            "id": "auto_sync_note",
                            "label": "保存笔记后自动同步盲文块",
                            "value": bool(cfg.get("auto_sync_note", False)),
                        },
                        {
                            "kind": "switch",
                            "id": "speech_assist",
                            "label": "阅读页启用语音朗读按钮",
                            "value": bool(cfg.get("speech_assist", True)),
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "write_braille_block", "label": "写入笔记盲文块", "variant": "secondary"},
                                {"id": "reveal_downloads", "label": "定位导出目录", "variant": "secondary"},
                            ],
                        },
                    ],
                },
                {
                    "id": "preview-card",
                    "title": "可读性指标与实时预览",
                    "items": [
                        {
                            "kind": "metrics",
                            "metrics": [
                                {"label": "段落数", "value": str(len(blocks))},
                                {"label": "盲文格数", "value": str(braille_count)},
                                {"label": "对比度", "value": pal["contrast"]},
                                {"label": "点阵步距", "value": f"{grid_px} px"},
                            ],
                        },
                        {
                            "kind": "preview",
                            "preview": preview_obj,
                        },
                    ],
                },
                {
                    "id": "logs-card",
                    "title": "输出目录与运行记录",
                    "items": [
                        {
                            "kind": "kv",
                            "rows": [note_row, dl_row],
                        },
                        {
                            "kind": "log_list",
                            "empty_text": "暂无点阵导出或盲文写入记录",
                            "entries": logs,
                        },
                    ],
                },
            ],
        }

    def sync_note_braille(self, bridge, note_path, cfg):
        content = self.read_note(bridge, note_path)
        blocks = parse_markdown_blocks(content)
        base = strip_embedded_block(content)
        section = build_embedded_braille_section(blocks, cfg.get("mode", "hybrid"))
        new_content = (base + "\n\n" + section + "\n") if base else (section + "\n")
        if new_content.strip() == (content or "").strip():
            return False, len(blocks)
        bridge.call_host("host.notes.write", {"path": note_path, "content": new_content})
        return True, len(blocks)

    def handle(self, bridge, method, params):
        if method == "plugin.initialize":
            dl = (params.get("downloads_dir") or "").strip()
            if dl:
                self.downloads_dir = dl
            self.notebook_root = (params.get("notebook_root") or "").strip()
            caps = params.get("ui_capabilities") or []
            if isinstance(caps, list):
                self.ui_capabilities = {str(c) for c in caps}
            return {"ready": True}

        if method == "plugin.render":
            cfg = self.load_config(bridge)
            if isinstance(params.get("values"), dict) and params["values"]:
                cfg = self.merge_values(cfg, params["values"])
                self.save_config(bridge, cfg)
            return {"page": self.build_page(bridge, cfg)}

        if method == "plugin.action":
            action_id = (params.get("action_id") or "").strip()
            cfg = self.load_config(bridge)
            cfg = self.merge_values(cfg, params.get("values") or {})
            self.save_config(bridge, cfg)

            notes, active = self.fetch_notes(bridge)
            target_path = self.resolve_target_note(cfg, notes, active)
            content = self.read_note(bridge, target_path)
            blocks = parse_markdown_blocks(content)

            os.makedirs(self.downloads_dir, exist_ok=True)
            stem = sanitize_filename(target_path or "block-note")

            if action_id == "open_reader":
                out_path = os.path.join(self.downloads_dir, f"{stem}-点阵阅读.html")
                html_doc = build_reader_html(target_path or "示例笔记", blocks, cfg)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(html_doc)
                self.last_status = f"已生成点阵阅读页（{now_hms()}）"
                self.append_log(bridge, os.path.basename(out_path), "已打开阅读页")
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "open_path": out_path,
                }

            if action_id == "export_tactile_svg":
                out_path = os.path.join(self.downloads_dir, f"{stem}-触觉点阵.svg")
                svg_doc = build_tactile_svg(target_path or "示例笔记", blocks)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(svg_doc)
                self.last_status = f"已导出触觉点阵 SVG（{now_hms()}）"
                self.append_log(bridge, os.path.basename(out_path), "已导出 SVG")
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "open_path": out_path,
                }

            if action_id == "write_braille_block":
                if not target_path:
                    self.last_status = "未检测到可写入的目标笔记"
                    return {
                        "values": cfg,
                        "page": self.build_page(bridge, cfg),
                        "status": self.last_status,
                    }
                changed, count = self.sync_note_braille(bridge, target_path, cfg)
                if changed:
                    self.last_status = f"已写入 {count} 段盲文点阵块到 {target_path}"
                    self.append_log(bridge, target_path, "已写回盲文块")
                else:
                    self.last_status = f"{target_path} 的盲文点阵块已是最新"
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                }

            if action_id == "reveal_downloads":
                self.last_status = f"已定位导出目录（{os.path.basename(self.downloads_dir)}）"
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "reveal_path": self.downloads_dir,
                }

            return {
                "values": cfg,
                "page": self.build_page(bridge, cfg),
                "status": f"未知操作：{action_id}",
            }

        if method == "plugin.event":
            event_name = params.get("event")
            note_path = (params.get("path") or "").strip()
            if event_name == "note.saved" and note_path:
                cfg = self.load_config(bridge)
                if cfg.get("auto_sync_note"):
                    changed, _ = self.sync_note_braille(bridge, note_path, cfg)
                    if changed:
                        self.last_status = f"保存自动同步盲文块：{note_path}（{now_hms()}）"
                        self.append_log(bridge, note_path, "保存自动同步")
            return {"handled": True}

        if method == "plugin.shutdown":
            return {"ok": True}

        raise RuntimeError(f"unsupported method: {method}")


if __name__ == "__main__":
    plugin = DotMatrixPlugin()
    HostBridge().serve(plugin.handle)
