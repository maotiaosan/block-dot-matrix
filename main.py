#!/usr/bin/env python3
import datetime
import html
import json
import os
import re
import sys

GRID_MODES = {
    "off": {"label": "无", "en": "None", "desc": "纯净纸面，无背景网格"},
    "grid": {"label": "方格", "en": "Grid", "desc": "与正文字号和行高对齐的等距方格线"},
    "dots": {"label": "点阵", "en": "Dots", "desc": "Thinkly 风格点阵纸背景，辅助视线水平追踪"},
}

CONTRAST_LEVELS = {
    "subtle": {
        "label": "柔和（Thinkly 默认）",
        "line_alpha": 0.07,
        "dot_alpha": 0.16,
        "dot_radius": 1.1,
        "rating": "标准纸感",
    },
    "clear": {
        "label": "清晰增强",
        "line_alpha": 0.14,
        "dot_alpha": 0.28,
        "dot_radius": 1.5,
        "rating": "弱视友好 AA+",
    },
    "high": {
        "label": "视障高对比",
        "line_alpha": 0.24,
        "dot_alpha": 0.42,
        "dot_radius": 1.9,
        "rating": "视障增强 AAA",
    },
}

PAPER_THEMES = {
    "paper": {
        "label": "浅色纸面",
        "preview_palette": "paper",
        "bg": "#ffffff",
        "surface": "#fbfbfc",
        "fg": "#181c24",
        "sub": "#4b5563",
        "rgb": "24, 28, 36",
        "accent": "#2f56a6",
        "accent_ink": "#ffffff",
        "border": "#dce1ea",
        "focus_bg": "rgba(47, 86, 166, 0.08)",
    },
    "warm": {
        "label": "暖色护眼",
        "preview_palette": "warm",
        "bg": "#faf6ee",
        "surface": "#f5efe2",
        "fg": "#241d15",
        "sub": "#5b4e3e",
        "rgb": "36, 29, 21",
        "accent": "#9a5210",
        "accent_ink": "#ffffff",
        "border": "#e1d6c3",
        "focus_bg": "rgba(154, 82, 16, 0.09)",
    },
    "dark_hc": {
        "label": "暗夜高对比",
        "preview_palette": "ink",
        "bg": "#0c0f16",
        "surface": "#121722",
        "fg": "#fff8dc",
        "sub": "#cbd5e1",
        "rgb": "255, 224, 102",
        "accent": "#ffe066",
        "accent_ink": "#0c0f16",
        "border": "rgba(255, 224, 102, 0.36)",
        "focus_bg": "rgba(255, 224, 102, 0.12)",
    },
}

DENSITY_CONFIG = {
    "compact": {"label": "紧凑 24px", "font_px": 15, "line_height": 1.6, "grid_px": 24},
    "standard": {"label": "标准 30px", "font_px": 17, "line_height": 1.75, "grid_px": 30},
    "relaxed": {"label": "宽松 38px", "font_px": 21, "line_height": 1.8, "grid_px": 38},
}

DEFAULT_CONFIG = {
    "target_note": "__active__",
    "grid_mode": "dots",
    "contrast_level": "clear",
    "paper_theme": "paper",
    "grid_density": "standard",
    "line_focus_guide": True,
    "large_text_boost": False,
}


def now_hms():
    return datetime.datetime.now().strftime("%H:%M:%S")


def sanitize_filename(name):
    stem = os.path.splitext(os.path.basename(name or "note"))[0]
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]+', "-", stem).strip(" .-")
    return cleaned or "note"


def clean_inline_markdown(line):
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[\1]", line)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"(\*\*|__|\*|_)", "", s)
    return s.strip()


def parse_markdown_blocks(content):
    blocks = []
    in_code = False
    for raw in (content or "").splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not line.strip():
            continue
        if in_code:
            blocks.append({"kind": "code", "level": 0, "text": line})
            continue
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", line.strip()):
            blocks.append({"kind": "hr", "level": 0, "text": ""})
            continue
        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_head:
            lvl = len(m_head.group(1))
            blocks.append({"kind": "heading", "level": lvl, "text": clean_inline_markdown(m_head.group(2))})
            continue
        m_quote = re.match(r"^>\s?(.*)$", line)
        if m_quote:
            blocks.append({"kind": "quote", "level": 0, "text": clean_inline_markdown(m_quote.group(1))})
            continue
        m_list = re.match(r"^[-*+]\s+(.*)$|^\d+\.\s+(.*)$", line.strip())
        if m_list:
            blocks.append({"kind": "list", "level": 0, "text": clean_inline_markdown(m_list.group(1) or m_list.group(2) or "")})
            continue
        text = clean_inline_markdown(line)
        if text:
            blocks.append({"kind": "paragraph", "level": 0, "text": text})
    return blocks


def build_canvas_html(note_path, blocks, cfg):
    mode = cfg.get("grid_mode", "dots")
    if mode not in GRID_MODES:
        mode = "dots"
    contrast_key = cfg.get("contrast_level", "clear")
    contrast = CONTRAST_LEVELS.get(contrast_key, CONTRAST_LEVELS["clear"])
    theme_key = cfg.get("paper_theme", "paper")
    theme = PAPER_THEMES.get(theme_key, PAPER_THEMES["paper"])
    dens_key = cfg.get("grid_density", "standard")
    dens = DENSITY_CONFIG.get(dens_key, DENSITY_CONFIG["standard"])
    focus_guide = bool(cfg.get("line_focus_guide", True))
    large_boost = bool(cfg.get("large_text_boost", False))

    base_font = dens["font_px"] + (4 if large_boost else 0)
    line_h = dens["line_height"]
    grid_size = round(base_font * line_h, 2)

    title_esc = html.escape(note_path or "未命名笔记")
    rows = []
    for idx, blk in enumerate(blocks, start=1):
        if blk["kind"] == "hr":
            rows.append('<hr class="doc-hr">')
            continue
        txt = html.escape(blk["text"])
        if blk["kind"] == "heading":
            lvl = min(max(blk["level"], 1), 3)
            rows.append(
                f'<div class="doc-block is-h{lvl}" tabindex="0" data-line="{idx}">'
                f'<span class="line-anchor" aria-hidden="true">{idx:02d}</span>'
                f'<h{lvl} class="block-text">{txt}</h{lvl}>'
                f'</div>'
            )
        elif blk["kind"] == "quote":
            rows.append(
                f'<div class="doc-block is-quote" tabindex="0" data-line="{idx}">'
                f'<span class="line-anchor" aria-hidden="true">{idx:02d}</span>'
                f'<blockquote class="block-text">{txt}</blockquote>'
                f'</div>'
            )
        elif blk["kind"] == "list":
            rows.append(
                f'<div class="doc-block is-list" tabindex="0" data-line="{idx}">'
                f'<span class="line-anchor" aria-hidden="true">{idx:02d}</span>'
                f'<p class="block-text"><span class="bullet-dot" aria-hidden="true"></span>{txt}</p>'
                f'</div>'
            )
        elif blk["kind"] == "code":
            rows.append(
                f'<div class="doc-block is-code" tabindex="0" data-line="{idx}">'
                f'<span class="line-anchor" aria-hidden="true">{idx:02d}</span>'
                f'<code class="block-text">{txt}</code>'
                f'</div>'
            )
        else:
            rows.append(
                f'<div class="doc-block" tabindex="0" data-line="{idx}">'
                f'<span class="line-anchor" aria-hidden="true">{idx:02d}</span>'
                f'<p class="block-text">{txt}</p>'
                f'</div>'
            )

    if not rows:
        rows.append(
            '<div class="doc-block" tabindex="0" data-line="1">'
            '<span class="line-anchor" aria-hidden="true">01</span>'
            '<p class="block-text">当前笔记暂无正文内容，请在 Block 编辑器中输入内容后重新打开。</p>'
            '</div>'
        )

    themes_json = json.dumps(PAPER_THEMES, ensure_ascii=False)
    contrasts_json = json.dumps(CONTRAST_LEVELS, ensure_ascii=False)

    return f"""<!doctype html>
<html lang="zh-CN" data-editor-grid="{mode}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_esc} · 画布点阵阅读</title>
<style>
:root {{
  --paper-bg: {theme['bg']};
  --paper-surface: {theme['surface']};
  --paper-fg: {theme['fg']};
  --paper-sub: {theme['sub']};
  --paper-accent: {theme['accent']};
  --paper-accent-ink: {theme['accent_ink']};
  --paper-border: {theme['border']};
  --paper-focus-bg: {theme['focus_bg']};
  --editor-font-size: {base_font}px;
  --editor-line-height: {line_h};
  --editor-grid-size: {grid_size}px;
  --editor-grid-line: rgba({theme['rgb']}, {contrast['line_alpha']});
  --editor-grid-dot: rgba({theme['rgb']}, {contrast['dot_alpha']});
  --editor-dot-r: {contrast['dot_radius']}px;
  --editor-grid-layers: none;
}}
:root[data-editor-grid="grid"] {{
  --editor-grid-layers:
    repeating-linear-gradient(to bottom, var(--editor-grid-line) 0 1px, transparent 1px var(--editor-grid-size)),
    repeating-linear-gradient(to right, var(--editor-grid-line) 0 1px, transparent 1px var(--editor-grid-size));
}}
:root[data-editor-grid="dots"] {{
  --editor-grid-layers:
    radial-gradient(circle at 50% 50%, var(--editor-grid-dot) var(--editor-dot-r), transparent calc(var(--editor-dot-r) + 0.55px));
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  background: var(--paper-surface);
  color: var(--paper-fg);
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
}}
.topbar {{
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 24px;
  background: var(--paper-bg);
  border-bottom: 1px solid var(--paper-border);
}}
.brand {{
  display: flex;
  align-items: baseline;
  gap: 10px;
}}
.brand strong {{ font-size: 15px; }}
.brand span {{
  font-size: 12px;
  color: var(--paper-sub);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}}
.toolbar-group {{
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}}
.seg {{
  display: inline-flex;
  padding: 3px;
  border-radius: 9px;
  background: var(--paper-surface);
  border: 1px solid var(--paper-border);
  gap: 2px;
}}
.seg button, .tool-btn {{
  min-height: 36px;
  padding: 0 12px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--paper-fg);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}}
.seg button[aria-pressed="true"] {{
  background: var(--paper-accent);
  color: var(--paper-accent-ink);
}}
.tool-btn {{
  border-color: var(--paper-border);
  background: var(--paper-bg);
}}
.tool-btn[aria-pressed="true"] {{
  border-color: var(--paper-accent);
  background: var(--paper-focus-bg);
  color: var(--paper-accent);
}}
.canvas-scroll {{
  min-height: calc(100vh - 64px);
  padding: 40px 24px 96px;
  background-color: var(--paper-bg);
  background-image: var(--editor-grid-layers);
  background-size: var(--editor-grid-size) var(--editor-grid-size);
  background-attachment: local;
}}
.editor-column {{
  max-width: 780px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.doc-block {{
  display: flex;
  align-items: baseline;
  gap: 16px;
  padding: 6px 12px;
  border-radius: 8px;
  border-left: 3px solid transparent;
  transition: background-color 120ms ease, border-color 120ms ease;
}}
body.focus-guide .doc-block:hover,
body.focus-guide .doc-block.is-focused,
body.focus-guide .doc-block:focus-visible {{
  background: var(--paper-focus-bg);
  border-left-color: var(--paper-accent);
  outline: none;
}}
.line-anchor {{
  width: 26px;
  flex-shrink: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--paper-sub);
  opacity: 0.72;
  user-select: none;
}}
.block-text {{
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: var(--editor-font-size);
  line-height: var(--editor-line-height);
  letter-spacing: 0.02em;
  word-break: break-word;
}}
.is-h1 .block-text {{ font-size: calc(var(--editor-font-size) * 1.55); font-weight: 700; line-height: 1.4; }}
.is-h2 .block-text {{ font-size: calc(var(--editor-font-size) * 1.28); font-weight: 700; line-height: 1.45; }}
.is-h3 .block-text {{ font-size: calc(var(--editor-font-size) * 1.12); font-weight: 650; }}
.is-quote .block-text {{
  padding-left: 14px;
  border-left: 3px solid var(--paper-accent);
  color: var(--paper-sub);
}}
.is-code .block-text {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: calc(var(--editor-font-size) * 0.9);
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--paper-surface);
  border: 1px solid var(--paper-border);
}}
.bullet-dot {{
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: var(--paper-accent);
  margin-right: 10px;
  vertical-align: middle;
}}
.doc-hr {{
  border: none;
  border-top: 1px dashed var(--paper-border);
  margin: 14px 0 14px 42px;
}}
@media print {{
  .topbar {{ display: none; }}
  .canvas-scroll {{ padding: 12mm; }}
}}
</style>
</head>
<body class="{'focus-guide' if focus_guide else ''}">
<header class="topbar" role="banner">
  <div class="brand">
    <strong>{title_esc}</strong>
    <span id="meta-info">画布 {GRID_MODES[mode]['label']} · {contrast['label']} · 步距 {grid_size}px</span>
  </div>
  <div class="toolbar-group" role="toolbar" aria-label="画布网格与可读性控制">
    <div class="seg" role="group" aria-label="编辑器网格">
      <button type="button" data-grid="off" aria-pressed="{str(mode == 'off').lower()}">无</button>
      <button type="button" data-grid="grid" aria-pressed="{str(mode == 'grid').lower()}">方格</button>
      <button type="button" data-grid="dots" aria-pressed="{str(mode == 'dots').lower()}">点阵</button>
    </div>
    <div class="seg" role="group" aria-label="对比度强度">
      <button type="button" data-contrast="subtle" aria-pressed="{str(contrast_key == 'subtle').lower()}">柔和</button>
      <button type="button" data-contrast="clear" aria-pressed="{str(contrast_key == 'clear').lower()}">清晰</button>
      <button type="button" data-contrast="high" aria-pressed="{str(contrast_key == 'high').lower()}">高对比</button>
    </div>
    <div class="seg" role="group" aria-label="纸面主题">
      <button type="button" data-theme="paper" aria-pressed="{str(theme_key == 'paper').lower()}">浅色</button>
      <button type="button" data-theme="warm" aria-pressed="{str(theme_key == 'warm').lower()}">暖纸</button>
      <button type="button" data-theme="dark_hc" aria-pressed="{str(theme_key == 'dark_hc').lower()}">暗夜</button>
    </div>
    <button type="button" id="btn-dec" class="tool-btn" aria-label="缩小字号">A-</button>
    <button type="button" id="btn-inc" class="tool-btn" aria-label="放大字号">A+</button>
    <button type="button" id="btn-focus" class="tool-btn" aria-pressed="{str(focus_guide).lower()}">行焦点</button>
  </div>
</header>
<main class="canvas-scroll" role="main">
  <div class="editor-column">
    {''.join(rows)}
  </div>
</main>
<script>
const THEMES = {themes_json};
const CONTRASTS = {contrasts_json};
const MODE_LABELS = {{ off: '无', grid: '方格', dots: '点阵' }};
let curGrid = {json.dumps(mode)};
let curContrast = {json.dumps(contrast_key)};
let curTheme = {json.dumps(theme_key)};
let curFont = {base_font};
const lineHeight = {line_h};

function syncVars() {{
  const t = THEMES[curTheme] || THEMES.paper;
  const c = CONTRASTS[curContrast] || CONTRASTS.clear;
  const gridPx = Math.round(curFont * lineHeight * 100) / 100;
  const r = document.documentElement.style;
  document.documentElement.setAttribute('data-editor-grid', curGrid);
  r.setProperty('--paper-bg', t.bg);
  r.setProperty('--paper-surface', t.surface);
  r.setProperty('--paper-fg', t.fg);
  r.setProperty('--paper-sub', t.sub);
  r.setProperty('--paper-accent', t.accent);
  r.setProperty('--paper-accent-ink', t.accent_ink);
  r.setProperty('--paper-border', t.border);
  r.setProperty('--paper-focus-bg', t.focus_bg);
  r.setProperty('--editor-font-size', curFont + 'px');
  r.setProperty('--editor-grid-size', gridPx + 'px');
  r.setProperty('--editor-grid-line', 'rgba(' + t.rgb + ', ' + c.line_alpha + ')');
  r.setProperty('--editor-grid-dot', 'rgba(' + t.rgb + ', ' + c.dot_alpha + ')');
  r.setProperty('--editor-dot-r', c.dot_radius + 'px');
  document.getElementById('meta-info').textContent =
    '画布 ' + MODE_LABELS[curGrid] + ' · ' + c.label + ' · 步距 ' + gridPx + 'px · 字号 ' + curFont + 'px';
}}

document.querySelectorAll('[data-grid]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    curGrid = btn.getAttribute('data-grid');
    document.querySelectorAll('[data-grid]').forEach(b => b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'));
    syncVars();
  }});
}});
document.querySelectorAll('[data-contrast]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    curContrast = btn.getAttribute('data-contrast');
    document.querySelectorAll('[data-contrast]').forEach(b => b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'));
    syncVars();
  }});
}});
document.querySelectorAll('[data-theme]').forEach(btn => {{
  btn.addEventListener('click', () => {{
    curTheme = btn.getAttribute('data-theme');
    document.querySelectorAll('[data-theme]').forEach(b => b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'));
    syncVars();
  }});
}});
document.getElementById('btn-dec').addEventListener('click', () => {{
  curFont = Math.max(14, curFont - 2);
  syncVars();
}});
document.getElementById('btn-inc').addEventListener('click', () => {{
  curFont = Math.min(34, curFont + 2);
  syncVars();
}});
document.getElementById('btn-focus').addEventListener('click', (e) => {{
  const on = document.body.classList.toggle('focus-guide');
  e.currentTarget.setAttribute('aria-pressed', on ? 'true' : 'false');
}});
document.querySelectorAll('.doc-block').forEach(el => {{
  el.addEventListener('click', () => {{
    document.querySelectorAll('.doc-block.is-focused').forEach(x => x.classList.remove('is-focused'));
    el.classList.add('is-focused');
  }});
}});
</script>
</body>
</html>
"""


def build_grid_paper_svg(note_path, blocks, cfg):
    """Export an A4 vector dot-grid / square-grid sheet (Thinkly canvas style, no Braille)."""
    mode = cfg.get("grid_mode", "dots")
    if mode not in GRID_MODES:
        mode = "dots"
    contrast = CONTRAST_LEVELS.get(cfg.get("contrast_level", "clear"), CONTRAST_LEVELS["clear"])
    theme = PAPER_THEMES.get(cfg.get("paper_theme", "paper"), PAPER_THEMES["paper"])
    dens = DENSITY_CONFIG.get(cfg.get("grid_density", "standard"), DENSITY_CONFIG["standard"])

    w, h = 794, 1123
    step = dens["grid_px"]
    dot_r = contrast["dot_radius"]
    dot_fill = f"rgba({theme['rgb']}, {contrast['dot_alpha']})"
    line_stroke = f"rgba({theme['rgb']}, {contrast['line_alpha']})"

    defs = []
    bg_fill = theme["bg"]
    pattern_rect = ""
    if mode == "dots":
        defs.append(
            f'<pattern id="dot-pattern" width="{step}" height="{step}" patternUnits="userSpaceOnUse">'
            f'<circle cx="{step / 2:.1f}" cy="{step / 2:.1f}" r="{dot_r}" fill="{dot_fill}"/>'
            f'</pattern>'
        )
        pattern_rect = f'<rect x="36" y="36" width="{w - 72}" height="{h - 72}" fill="url(#dot-pattern)"/>'
    elif mode == "grid":
        defs.append(
            f'<pattern id="grid-pattern" width="{step}" height="{step}" patternUnits="userSpaceOnUse">'
            f'<path d="M {step} 0 L 0 0 0 {step}" fill="none" stroke="{line_stroke}" stroke-width="1"/>'
            f'</pattern>'
        )
        pattern_rect = f'<rect x="36" y="36" width="{w - 72}" height="{h - 72}" fill="url(#grid-pattern)"/>'

    lines_svg = []
    y = 128
    for idx, blk in enumerate(blocks[:22], start=1):
        if blk["kind"] == "hr":
            lines_svg.append(f'<line x1="64" y1="{y}" x2="{w - 64}" y2="{y}" stroke="{theme["border"]}" stroke-dasharray="4 4"/>')
            y += step
            continue
        text = blk["text"][:46]
        size = 24 if blk["kind"] == "heading" and blk["level"] == 1 else 19 if blk["kind"] == "heading" else 16
        weight = "700" if blk["kind"] == "heading" else "500"
        lines_svg.append(
            f'<text x="64" y="{y}" font-family="monospace" font-size="11" fill="{theme["sub"]}">{idx:02d}</text>'
            f'<text x="96" y="{y}" font-family="sans-serif" font-size="{size}" font-weight="{weight}" fill="{theme["fg"]}">{html.escape(text)}</text>'
        )
        y += max(step, int(size * 1.85))
        if y > h - 72:
            break

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<defs>{"".join(defs)}</defs>',
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{bg_fill}"/>',
        pattern_rect,
        f'<text x="64" y="68" font-family="sans-serif" font-size="12" font-weight="700" fill="{theme["accent"]}">BLOCK CANVAS DOTS · {GRID_MODES[mode]["label"]}画布（{contrast["label"]} · {step}px）</text>',
        f'<text x="64" y="92" font-family="sans-serif" font-size="18" font-weight="700" fill="{theme["fg"]}">{html.escape(note_path or "note.md")}</text>',
        f'<line x1="64" y1="104" x2="{w - 64}" y2="104" stroke="{theme["border"]}" stroke-width="1.2"/>',
        *lines_svg,
        "</svg>",
    ])


def build_canvas_css(cfg):
    mode = cfg.get("grid_mode", "dots")
    contrast = CONTRAST_LEVELS.get(cfg.get("contrast_level", "clear"), CONTRAST_LEVELS["clear"])
    theme = PAPER_THEMES.get(cfg.get("paper_theme", "paper"), PAPER_THEMES["paper"])
    dens = DENSITY_CONFIG.get(cfg.get("grid_density", "standard"), DENSITY_CONFIG["standard"])
    return f"""/* Thinkly-style Editor Canvas Grid & Dots (exported by block-dot-matrix) */
:root[data-block-editor-grid] {{
  --editor-font-size: {dens['font_px']}px;
  --editor-line-height: {dens['line_height']};
  --block-editor-grid-size: calc(var(--editor-font-size) * var(--editor-line-height));
  --block-editor-grid-line: rgba({theme['rgb']}, {contrast['line_alpha']});
  --block-editor-grid-dot: rgba({theme['rgb']}, {contrast['dot_alpha']});
  --block-editor-grid-layers:
    repeating-linear-gradient(to bottom, var(--block-editor-grid-line) 0 1px, transparent 1px var(--block-editor-grid-size)),
    repeating-linear-gradient(to right, var(--block-editor-grid-line) 0 1px, transparent 1px var(--block-editor-grid-size));
}}

:root[data-block-editor-grid="dots"] {{
  --block-editor-grid-layers:
    radial-gradient(circle at 50% 50%, var(--block-editor-grid-dot) {contrast['dot_radius']}px, transparent {contrast['dot_radius'] + 0.5:.2f}px) 0 0 / var(--block-editor-grid-size) var(--block-editor-grid-size) round local;
}}

/* Active preset: data-block-editor-grid="{mode}" ({GRID_MODES[mode]['label']} · {contrast['label']}) */
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


class CanvasDotsPlugin:
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
                return res["value"][:10]
        except Exception:
            pass
        return []

    def append_log(self, bridge, title, status):
        logs = self.load_logs(bridge)
        logs.insert(0, {"title": title, "time": now_hms(), "status": status})
        try:
            bridge.call_host("host.storage.set", {"key": "logs", "value": logs[:10]})
        except Exception:
            pass

    def merge_values(self, cfg, values):
        if not isinstance(values, dict):
            return cfg
        updated = dict(cfg)
        for key in ("target_note", "grid_mode", "contrast_level", "paper_theme", "grid_density"):
            if key in values and isinstance(values[key], str):
                updated[key] = values[key]
        for key in ("line_focus_guide", "large_text_boost"):
            if key in values and isinstance(values[key], bool):
                updated[key] = values[key]
        return updated

    def fetch_notes(self, bridge):
        notes, active = [], ""
        try:
            res = bridge.call_host("host.notes.list", {})
            notes = [n.get("path", "") for n in res.get("notes", []) if n.get("path")]
        except Exception:
            pass
        try:
            res = bridge.call_host("host.notes.active", {})
            active = (res.get("path") or "").strip()
        except Exception:
            pass
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

        mode = cfg.get("grid_mode", "dots")
        if mode not in GRID_MODES:
            mode = "dots"
        contrast_key = cfg.get("contrast_level", "clear")
        if contrast_key not in CONTRAST_LEVELS:
            contrast_key = "clear"
        theme_key = cfg.get("paper_theme", "paper")
        if theme_key not in PAPER_THEMES:
            theme_key = "paper"
        dens_key = cfg.get("grid_density", "standard")
        if dens_key not in DENSITY_CONFIG:
            dens_key = "standard"

        contrast = CONTRAST_LEVELS[contrast_key]
        theme = PAPER_THEMES[theme_key]
        dens = DENSITY_CONFIG[dens_key]
        target_path = self.resolve_target_note(cfg, notes, active)
        blocks = parse_markdown_blocks(self.read_note(bridge, target_path))

        preview_lines = []
        for idx, blk in enumerate(blocks[:5], start=1):
            if blk["kind"] == "heading" and blk["level"] == 1:
                preview_lines.append(f"# {blk['text']}")
            elif blk["kind"] == "heading":
                preview_lines.append(f"## {blk['text']}")
            elif blk["kind"] == "quote":
                preview_lines.append(f"> {blk['text']}")
            elif blk["kind"] != "hr":
                preview_lines.append(f"[{idx}] {blk['text']}")

        if not preview_lines:
            preview_lines = [
                "# 画布点阵阅读预览",
                "## Thinkly 同款编辑器网格（无 / 方格 / 点阵）",
                "> 点阵步距随正文字号与行高自动对齐，帮助弱视用户稳定追踪每一行。",
            ]

        dl_name = os.path.basename(self.downloads_dir.rstrip(os.sep)) or "Downloads"
        dl_row = {"label": "导出目录", "value": dl_name}
        if "kv_tooltip" in self.ui_capabilities:
            dl_row["tooltip"] = self.downloads_dir

        note_row = {"label": "目标笔记", "value": target_path or "未打开笔记本"}
        if "kv_tooltip" in self.ui_capabilities and self.notebook_root and target_path:
            note_row["tooltip"] = os.path.join(self.notebook_root, target_path)

        return {
            "title": "画布点阵",
            "status": self.last_status,
            "header_actions": [
                {"id": "open_reader", "label": "打开点阵画布页", "variant": "primary"},
                {"id": "export_grid_svg", "label": "导出 A4 点阵纸", "variant": "secondary"},
            ],
            "cards": [
                {
                    "id": "canvas-card",
                    "title": "画布（Thinkly 编辑器网格）",
                    "items": [
                        {
                            "kind": "segmented",
                            "id": "grid_mode",
                            "label": "编辑器网格",
                            "value": mode,
                            "options": [
                                {"value": "off", "label": "无"},
                                {"value": "grid", "label": "方格"},
                                {"value": "dots", "label": "点阵"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "contrast_level",
                            "label": "点阵对比度",
                            "value": contrast_key,
                            "options": [
                                {"value": "subtle", "label": "柔和"},
                                {"value": "clear", "label": "清晰增强"},
                                {"value": "high", "label": "视障高对比"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "grid_density",
                            "label": "行高步距",
                            "value": dens_key,
                            "options": [
                                {"value": "compact", "label": "紧凑 24px"},
                                {"value": "standard", "label": "标准 30px"},
                                {"value": "relaxed", "label": "宽松 38px"},
                            ],
                        },
                        {
                            "kind": "segmented",
                            "id": "paper_theme",
                            "label": "纸面主题",
                            "value": theme_key,
                            "options": [
                                {"value": "paper", "label": "浅色纸面"},
                                {"value": "warm", "label": "暖色护眼"},
                                {"value": "dark_hc", "label": "暗夜高对比"},
                            ],
                        },
                        {
                            "kind": "switch",
                            "id": "line_focus_guide",
                            "label": "开启行焦点防串行引导",
                            "value": bool(cfg.get("line_focus_guide", True)),
                        },
                        {
                            "kind": "switch",
                            "id": "large_text_boost",
                            "label": "弱视大字增强（字号 +4px）",
                            "value": bool(cfg.get("large_text_boost", False)),
                        },
                        {
                            "kind": "select",
                            "id": "target_note",
                            "label": "预览笔记",
                            "value": selected_note_val,
                            "options": note_options,
                        },
                        {
                            "kind": "actions",
                            "buttons": [
                                {"id": "export_css", "label": "导出网格 CSS", "variant": "secondary"},
                                {"id": "reveal_downloads", "label": "定位导出目录", "variant": "secondary"},
                            ],
                        },
                    ],
                },
                {
                    "id": "preview-card",
                    "title": "画布参数与实时预览",
                    "items": [
                        {
                            "kind": "metrics",
                            "metrics": [
                                {"label": "网格样式", "value": GRID_MODES[mode]["label"]},
                                {"label": "网格步距", "value": f"{dens['grid_px']} px"},
                                {"label": "点径 / 透明", "value": f"{contrast['dot_radius']}px / {int(contrast['dot_alpha'] * 100)}%"},
                                {"label": "可读性等级", "value": contrast["rating"]},
                            ],
                        },
                        {
                            "kind": "preview",
                            "preview": {
                                "variant": "article",
                                "palette": theme["preview_palette"],
                                "title": f"{GRID_MODES[mode]['label']}画布 · {target_path or '示例笔记'}",
                                "badge": f"{theme['label']} · {contrast['label']}",
                                "subtitle": f"{sanitize_filename(target_path)}-点阵画布.html",
                                "body": "\n".join(preview_lines),
                            },
                        },
                    ],
                },
                {
                    "id": "logs-card",
                    "title": "输出目录与最近记录",
                    "items": [
                        {
                            "kind": "kv",
                            "rows": [note_row, dl_row],
                        },
                        {
                            "kind": "log_list",
                            "empty_text": "暂无画布导出记录",
                            "entries": self.load_logs(bridge),
                        },
                    ],
                },
            ],
        }

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
            blocks = parse_markdown_blocks(self.read_note(bridge, target_path))
            os.makedirs(self.downloads_dir, exist_ok=True)
            stem = sanitize_filename(target_path or "block-note")

            if action_id == "open_reader":
                out_path = os.path.join(self.downloads_dir, f"{stem}-点阵画布.html")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(build_canvas_html(target_path or "示例笔记", blocks, cfg))
                self.last_status = f"已打开点阵画布页（{now_hms()}）"
                self.append_log(bridge, os.path.basename(out_path), f"{GRID_MODES[cfg['grid_mode']]['label']}画布")
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "open_path": out_path,
                }

            if action_id == "export_grid_svg":
                out_path = os.path.join(self.downloads_dir, f"{stem}-点阵纸.svg")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(build_grid_paper_svg(target_path or "示例笔记", blocks, cfg))
                self.last_status = f"已导出 A4 点阵纸（{now_hms()}）"
                self.append_log(bridge, os.path.basename(out_path), "A4 点阵纸")
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "open_path": out_path,
                }

            if action_id == "export_css":
                out_path = os.path.join(self.downloads_dir, "block-canvas-dots.css")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(build_canvas_css(cfg))
                self.last_status = f"已导出 Thinkly 风格网格 CSS（{now_hms()}）"
                self.append_log(bridge, os.path.basename(out_path), "CSS 样式")
                return {
                    "values": cfg,
                    "page": self.build_page(bridge, cfg),
                    "status": self.last_status,
                    "reveal_path": out_path,
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

        if method == "plugin.shutdown":
            return {"ok": True}

        raise RuntimeError(f"unsupported method: {method}")


if __name__ == "__main__":
    plugin = CanvasDotsPlugin()
    HostBridge().serve(plugin.handle)
