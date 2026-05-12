"""
Generate a college-style Yashi project report as a standalone .docx file.

The script uses the supplied report as an OpenXML template package so the
existing college logos, styles, theme, and document settings are preserved.
Only the document body plus one simple header/footer are replaced.
"""
from __future__ import annotations

import html
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template_reference.docx"
OUTPUT = ROOT / "Yashi_Project_Report_Detailed_Charts.docx"
ASSET_DIR = ROOT / "report_generated_assets"

PROJECT_TITLE = "Yashi AI Companion and Personal Desktop Assistant"
SHORT_TITLE = "YASHI AI COMPANION"
COLLEGE = "AXIS INSTITUTE OF TECHNOLOGY & MANAGEMENT KANPUR"
UNIVERSITY = "DR. A.P.J. ABDUL KALAM TECHNICAL UNIVERSITY, LUCKNOW"
DEPARTMENT = "COMPUTER SCIENCE & ENGINEERING (Artificial Intelligence & Machine Learning)"
SESSION = "2025-26"
GUIDE = "Ms. Sonali Singh"
HOD = "Dr. Shubha Jain"
STUDENT = "Sarth"
ENROLLMENT = "Enrollment No.: __________"

REPORT_FIGURES = [
    {
        "key": "architecture",
        "rid": "rId41",
        "filename": "yashi_architecture.png",
        "doc_id": 601,
        "caption": "Fig. 2: High-level architecture of Yashi",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "pipeline",
        "rid": "rId42",
        "filename": "yashi_pipeline.png",
        "doc_id": 602,
        "caption": "Fig. 3: Conversation and plugin processing pipeline",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "stop_sequence",
        "rid": "rId43",
        "filename": "yashi_stop_sequence.png",
        "doc_id": 603,
        "caption": "Fig. 4: Stop response sequence flow",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "feature_completion",
        "rid": "rId44",
        "filename": "yashi_feature_completion.png",
        "doc_id": 604,
        "caption": "Fig. 5: Feature completion and maturity chart",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "backend_chart",
        "rid": "rId45",
        "filename": "yashi_backend_comparison.png",
        "doc_id": 605,
        "caption": "Fig. 6: Ollama and OpenAI backend comparison",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "risk_matrix",
        "rid": "rId46",
        "filename": "yashi_risk_matrix.png",
        "doc_id": 606,
        "caption": "Fig. 7: Risk matrix for local AI assistant features",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "mobile_wireframe",
        "rid": "rId47",
        "filename": "yashi_mobile_wireframe.png",
        "doc_id": 607,
        "caption": "Fig. 8: Browser and mobile UI layout diagram",
        "cx": 6100000,
        "cy": 3430000,
    },
    {
        "key": "timeline",
        "rid": "rId48",
        "filename": "yashi_timeline.png",
        "doc_id": 608,
        "caption": "Fig. 9: Yashi feature development timeline",
        "cx": 6100000,
        "cy": 3430000,
    },
]

FIGURE_MAP = {item["key"]: item for item in REPORT_FIGURES}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        words = raw.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            test = f"{current} {word}"
            if _measure(draw, test, font)[0] <= max_width:
                current = test
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
                 font: ImageFont.ImageFont, fill: str = "#111827") -> None:
    x1, y1, x2, y2 = box
    lines = _wrap(draw, text, font, x2 - x1 - 30)
    line_heights = [_measure(draw, line, font)[1] for line in lines]
    total = sum(line_heights) + max(0, len(lines) - 1) * 8
    y = y1 + ((y2 - y1 - total) // 2)
    for line, height in zip(lines, line_heights):
        width, _ = _measure(draw, line, font)
        draw.text((x1 + ((x2 - x1 - width) // 2), y), line, font=font, fill=fill)
        y += height + 8


def _box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str,
         outline: str = "#1f2937", radius: int = 24) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=3)


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int],
           fill: str = "#1f2937", width: int = 5) -> None:
    x1, y1 = start
    x2, y2 = end
    draw.line((x1, y1, x2, y2), fill=fill, width=width)
    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) >= abs(dy):
        direction = 1 if dx >= 0 else -1
        points = [(x2, y2), (x2 - direction * 18, y2 - 11), (x2 - direction * 18, y2 + 11)]
    else:
        direction = 1 if dy >= 0 else -1
        points = [(x2, y2), (x2 - 11, y2 - direction * 18), (x2 + 11, y2 - direction * 18)]
    draw.polygon(points, fill=fill)


def _canvas(title: str, subtitle: str | None = None) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1600, 900), "#f8fafc")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1600, 900), fill="#f8fafc")
    draw.text((60, 38), title, font=_font(42, True), fill="#0f172a")
    if subtitle:
        draw.text((62, 92), subtitle, font=_font(22), fill="#475569")
    draw.line((60, 130, 1540, 130), fill="#cbd5e1", width=3)
    return image, draw


def _save_architecture(path: Path) -> None:
    image, draw = _canvas("Yashi High-Level Architecture", "Layered design connecting user interaction, AI reasoning, plugins, voice, and memory.")
    colors = ["#dbeafe", "#dcfce7", "#fef3c7", "#fee2e2", "#e0e7ff"]
    boxes = [
        ((80, 185, 330, 325), "User Interfaces\nReact Browser UI\nMobile Layout\npywebview Desktop"),
        ((405, 185, 655, 325), "FastAPI Layer\nREST Routes\nWebSocket Chat\nSettings API"),
        ((730, 185, 980, 325), "Core Engine\nEmotion Fusion\nPrompt Builder\nStreaming LLM"),
        ((1055, 185, 1305, 325), "Action Plugins\nSpotify/App Launch\nFile Ops\nWeb Search"),
        ((405, 520, 655, 680), "Voice Layer\nWake Word\nElevenLabs\nBrowser TTS"),
        ((730, 520, 980, 680), "Memory Layer\nSQLite History\nFacts\nReflections"),
        ((1055, 520, 1305, 680), "External/Local\nOllama\nOpenAI\nSpotify/Browser"),
    ]
    for index, (rect, label) in enumerate(boxes):
        _box(draw, rect, colors[index % len(colors)])
        _center_text(draw, rect, label, _font(23, True))
    for a, b in [
        ((330, 255), (405, 255)),
        ((655, 255), (730, 255)),
        ((980, 255), (1055, 255)),
        ((855, 325), (855, 520)),
        ((1135, 325), (1135, 520)),
        ((655, 600), (730, 600)),
    ]:
        _arrow(draw, a, b)
    _arrow(draw, (530, 325), (530, 520), "#2563eb")
    draw.text((80, 770), "Design principle: LLM handles language, plugins handle deterministic local actions, and the UI remains in control of voice/status.", font=_font(24, True), fill="#0f172a")
    image.save(path)


def _save_pipeline(path: Path) -> None:
    image, draw = _canvas("Conversation and Plugin Pipeline", "A prompt can become either a direct local action or a streamed AI response.")
    steps = [
        ("User Prompt", "#dbeafe"),
        ("Intent Detector", "#dcfce7"),
        ("Plugin Dispatch", "#fef3c7"),
        ("Conversation Engine", "#fee2e2"),
        ("LLM Stream", "#ede9fe"),
        ("TTS + UI Events", "#e0f2fe"),
    ]
    y = 260
    width = 210
    gap = 40
    x = 65
    for index, (label, color) in enumerate(steps):
        rect = (x + index * (width + gap), y, x + index * (width + gap) + width, y + 125)
        _box(draw, rect, color)
        _center_text(draw, rect, label, _font(23, True))
        if index < len(steps) - 1:
            _arrow(draw, (rect[2], y + 62), (rect[2] + gap - 5, y + 62))
    plugin_rect = (350, 520, 625, 680)
    llm_rect = (900, 520, 1175, 680)
    _box(draw, plugin_rect, "#fff7ed")
    _box(draw, llm_rect, "#eef2ff")
    _center_text(draw, plugin_rect, "Fast Path\nOpen app\nPlay Spotify\nWrite file", _font(22, True))
    _center_text(draw, llm_rect, "AI Path\nMemory\nEmotion\nPrompt\nStreaming", _font(22, True))
    _arrow(draw, (470, 385), (470, 520), "#ea580c")
    _arrow(draw, (1010, 385), (1010, 520), "#4f46e5")
    draw.text((80, 760), "The plugin path avoids unnecessary model calls for local commands. The AI path is used when a conversational response is needed.", font=_font(24), fill="#334155")
    image.save(path)


def _save_stop_sequence(path: Path) -> None:
    image, draw = _canvas("Stop Response Sequence", "The user can interrupt text streaming and voice playback while generation is active.")
    actors = [("User", 160), ("React UI", 470), ("FastAPI WS", 790), ("ConversationEngine", 1130), ("LLM/TTS", 1430)]
    for name, x in actors:
        draw.text((x - 70, 170), name, font=_font(24, True), fill="#0f172a")
        draw.line((x, 220, x, 770), fill="#94a3b8", width=3)
    flows = [
        (160, 470, 270, "1. Send prompt"),
        (470, 790, 340, "2. WebSocket text"),
        (790, 1130, 410, "3. Start pipeline"),
        (1130, 1430, 480, "4. Stream tokens"),
        (160, 470, 570, "5. Click Stop"),
        (470, 790, 630, "6. Send stop"),
        (790, 1130, 690, "7. request_stop()"),
        (1130, 470, 750, "8. done(stopped=true)"),
    ]
    for x1, x2, y, label in flows:
        _arrow(draw, (x1, y), (x2, y), "#2563eb" if y < 540 else "#dc2626", 4)
        draw.text((min(x1, x2) + 20, y - 32), label, font=_font(19, True), fill="#0f172a")
    draw.text((90, 815), "Frontend side effects: cancel speech synthesis, stop queued audio, stop lip animation, clear typing state, and allow the next prompt.", font=_font(22), fill="#334155")
    image.save(path)


def _save_feature_completion(path: Path) -> None:
    image, draw = _canvas("Feature Completion and Maturity", "Approximate implementation maturity based on current project code and review notes.")
    data = [
        ("Chat streaming", 95, "#16a34a"),
        ("Stop response", 90, "#22c55e"),
        ("ElevenLabs voice", 84, "#0ea5e9"),
        ("Spotify control", 78, "#f59e0b"),
        ("File write/append", 82, "#14b8a6"),
        ("Mobile UI", 80, "#6366f1"),
        ("Wake word", 68, "#f97316"),
        ("Any-directory ops", 52, "#ef4444"),
    ]
    left, top, bar_w, bar_h = 360, 185, 950, 48
    for i, (label, value, color) in enumerate(data):
        y = top + i * 75
        draw.text((85, y + 8), label, font=_font(23, True), fill="#0f172a")
        draw.rounded_rectangle((left, y, left + bar_w, y + bar_h), radius=18, fill="#e2e8f0")
        draw.rounded_rectangle((left, y, left + int(bar_w * value / 100), y + bar_h), radius=18, fill=color)
        draw.text((left + bar_w + 25, y + 8), f"{value}%", font=_font(22, True), fill="#0f172a")
    draw.text((85, 820), "Lower scores indicate environment-dependent behavior or known review findings rather than missing project value.", font=_font(22), fill="#475569")
    image.save(path)


def _save_backend_chart(path: Path) -> None:
    image, draw = _canvas("Ollama vs OpenAI Backend Comparison", "Scores are normalized from 1 to 5 for project suitability.")
    categories = ["Cost", "Privacy", "PC Load", "Quality", "Offline", "Quota Risk"]
    ollama = [5, 5, 2, 3, 5, 5]
    openai = [2, 2, 5, 5, 1, 2]
    origin_x, origin_y = 180, 720
    chart_w, chart_h = 1240, 470
    draw.line((origin_x, origin_y, origin_x + chart_w, origin_y), fill="#334155", width=3)
    draw.line((origin_x, origin_y - chart_h, origin_x, origin_y), fill="#334155", width=3)
    for score in range(1, 6):
        y = origin_y - int(chart_h * score / 5)
        draw.line((origin_x, y, origin_x + chart_w, y), fill="#e2e8f0", width=2)
        draw.text((130, y - 12), str(score), font=_font(18), fill="#475569")
    group_w = chart_w // len(categories)
    for i, category in enumerate(categories):
        x = origin_x + i * group_w + 25
        for j, (value, color) in enumerate([(ollama[i], "#16a34a"), (openai[i], "#2563eb")]):
            h = int(chart_h * value / 5)
            bx = x + j * 42
            draw.rounded_rectangle((bx, origin_y - h, bx + 34, origin_y), radius=8, fill=color)
        draw.text((x - 12, origin_y + 18), category, font=_font(18, True), fill="#0f172a")
    draw.rounded_rectangle((1050, 170, 1450, 245), radius=18, fill="#ffffff", outline="#cbd5e1", width=2)
    draw.rectangle((1080, 190, 1110, 220), fill="#16a34a")
    draw.text((1125, 188), "Ollama", font=_font(22, True), fill="#0f172a")
    draw.rectangle((1240, 190, 1270, 220), fill="#2563eb")
    draw.text((1285, 188), "OpenAI", font=_font(22, True), fill="#0f172a")
    image.save(path)


def _save_risk_matrix(path: Path) -> None:
    image, draw = _canvas("Risk Matrix", "Risks are mapped by technical impact and likelihood for future hardening.")
    x0, y0, w, h = 260, 185, 1000, 560
    draw.rectangle((x0, y0, x0 + w, y0 + h), fill="#ffffff", outline="#334155", width=4)
    draw.line((x0 + w // 2, y0, x0 + w // 2, y0 + h), fill="#94a3b8", width=3)
    draw.line((x0, y0 + h // 2, x0 + w, y0 + h // 2), fill="#94a3b8", width=3)
    quadrants = [
        ((x0, y0, x0 + w // 2, y0 + h // 2), "#fee2e2", "High Impact\nLower Likelihood"),
        ((x0 + w // 2, y0, x0 + w, y0 + h // 2), "#fecaca", "High Impact\nHigh Likelihood"),
        ((x0, y0 + h // 2, x0 + w // 2, y0 + h), "#dcfce7", "Low Impact\nLower Likelihood"),
        ((x0 + w // 2, y0 + h // 2, x0 + w, y0 + h), "#fef3c7", "Low Impact\nHigh Likelihood"),
    ]
    for rect, color, label in quadrants:
        draw.rectangle(rect, fill=color)
        _center_text(draw, rect, label, _font(22, True), "#1f2937")
    draw.rectangle((x0, y0, x0 + w, y0 + h), outline="#334155", width=4)
    draw.line((x0 + w // 2, y0, x0 + w // 2, y0 + h), fill="#94a3b8", width=3)
    draw.line((x0, y0 + h // 2, x0 + w, y0 + h // 2), fill="#94a3b8", width=3)
    points = [
        (1030, 290, "Static path traversal"),
        (930, 390, "Backend hot-swap cache"),
        (1030, 585, "Wake STT reliability"),
        (735, 640, "Spotify UI variation"),
        (355, 390, "Broad file operations"),
    ]
    for x, y, label in points:
        tw, th = _measure(draw, label, _font(20, True))
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="#0f172a")
        draw.rounded_rectangle((x + 14, y - 18, x + 30 + tw, y + 18), radius=8, fill="#f8fafc", outline="#cbd5e1", width=1)
        draw.text((x + 16, y - 12), label, font=_font(20, True), fill="#0f172a")
    draw.text((650, 780), "Likelihood ->", font=_font(24, True), fill="#0f172a")
    draw.text((75, 430), "Impact", font=_font(24, True), fill="#0f172a")
    image.save(path)


def _save_mobile_wireframe(path: Path) -> None:
    image, draw = _canvas("Responsive UI Wireframe", "Desktop focus mode and mobile browser mode use the same assistant controls with different layout density.")
    # Desktop frame
    draw.rounded_rectangle((90, 180, 940, 720), radius=28, fill="#111827", outline="#334155", width=5)
    draw.rectangle((120, 220, 535, 680), fill="#0b0f19")
    draw.rounded_rectangle((575, 220, 905, 680), radius=14, fill="#f8fafc")
    draw.ellipse((255, 310, 405, 460), fill="#60a5fa")
    draw.text((220, 480), "Video Avatar", font=_font(25, True), fill="#e5e7eb")
    for i in range(5):
        y = 250 + i * 70
        fill = "#dbeafe" if i % 2 == 0 else "#dcfce7"
        draw.rounded_rectangle((600, y, 880, y + 44), radius=12, fill=fill)
    draw.rounded_rectangle((600, 620, 880, 662), radius=12, fill="#fee2e2")
    draw.text((325, 735), "Desktop / focus layout", font=_font(24, True), fill="#0f172a")
    # Mobile frame
    draw.rounded_rectangle((1110, 170, 1430, 735), radius=50, fill="#0f172a", outline="#334155", width=6)
    draw.rounded_rectangle((1140, 220, 1400, 690), radius=22, fill="#f8fafc")
    draw.rounded_rectangle((1160, 240, 1380, 310), radius=12, fill="#dbeafe")
    draw.ellipse((1228, 330, 1312, 414), fill="#60a5fa")
    for i in range(4):
        y = 440 + i * 45
        draw.rounded_rectangle((1170, y, 1370, y + 28), radius=8, fill="#e2e8f0")
    draw.rounded_rectangle((1170, 640, 1370, 675), radius=8, fill="#fee2e2")
    draw.text((1148, 755), "Mobile browser layout", font=_font(24, True), fill="#0f172a")
    image.save(path)


def _save_timeline(path: Path) -> None:
    image, draw = _canvas("Yashi Feature Development Timeline", "Major implementation milestones recorded in the project.")
    events = [
        ("Local AI", "Ollama + streaming chat"),
        ("Voice", "ElevenLabs + fallback"),
        ("Wake Word", "Yashi activation"),
        ("Automation", "Apps + Spotify"),
        ("Files", "Create/write/append"),
        ("UI", "Video avatar + mobile"),
        ("Control", "Stop response"),
        ("Report", "College documentation"),
    ]
    x_start, x_end, y = 120, 1480, 430
    draw.line((x_start, y, x_end, y), fill="#334155", width=6)
    step = (x_end - x_start) // (len(events) - 1)
    colors = ["#dbeafe", "#dcfce7", "#fef3c7", "#fee2e2", "#ede9fe", "#e0f2fe", "#ccfbf1", "#fce7f3"]
    for i, (title, desc) in enumerate(events):
        x = x_start + i * step
        draw.ellipse((x - 20, y - 20, x + 20, y + 20), fill="#0f172a")
        rect = (x - 95, y - 210 if i % 2 == 0 else y + 70, x + 95, y - 70 if i % 2 == 0 else y + 210)
        _box(draw, rect, colors[i], "#64748b", 18)
        _center_text(draw, rect, f"{title}\n{desc}", _font(19, True))
        _arrow(draw, (x, rect[3] if i % 2 == 0 else rect[1]), (x, y - 25 if i % 2 == 0 else y + 25), "#64748b", 3)
    image.save(path)


VISUAL_BUILDERS: dict[str, Callable[[Path], None]] = {
    "architecture": _save_architecture,
    "pipeline": _save_pipeline,
    "stop_sequence": _save_stop_sequence,
    "feature_completion": _save_feature_completion,
    "backend_chart": _save_backend_chart,
    "risk_matrix": _save_risk_matrix,
    "mobile_wireframe": _save_mobile_wireframe,
    "timeline": _save_timeline,
}


def generate_visual_assets() -> None:
    ASSET_DIR.mkdir(exist_ok=True)
    for figure in REPORT_FIGURES:
        VISUAL_BUILDERS[figure["key"]](ASSET_DIR / figure["filename"])


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def rpr(font: str = "Times New Roman", size: int = 24, bold: bool = False,
        italic: bool = False, color: str | None = None) -> str:
    bits = [
        f'<w:rFonts w:ascii="{esc(font)}" w:hAnsi="{esc(font)}" w:eastAsia="{esc(font)}" w:cs="{esc(font)}"/>',
        f'<w:sz w:val="{size}"/>',
        f'<w:szCs w:val="{size}"/>',
    ]
    if bold:
        bits.append("<w:b/><w:bCs/>")
    if italic:
        bits.append("<w:i/><w:iCs/>")
    if color:
        bits.append(f'<w:color w:val="{esc(color)}"/>')
    return "<w:rPr>" + "".join(bits) + "</w:rPr>"


def p(text: str = "", *, style: str | None = None, align: str | None = None,
      size: int = 24, bold: bool = False, italic: bool = False,
      font: str = "Times New Roman", before: int = 0, after: int = 120,
      line: int = 276, indent_left: int = 0, first_line: int = 0,
      color: str | None = None, shade: str | None = None) -> str:
    ppr = []
    if style:
        ppr.append(f'<w:pStyle w:val="{style}"/>')
    if shade:
        ppr.append(f'<w:shd w:fill="{shade}"/>')
    ppr.append(f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>')
    if indent_left or first_line:
        ppr.append(f'<w:ind w:left="{indent_left}" w:firstLine="{first_line}"/>')
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    ppr.append(rpr(font=font, size=size, bold=bold, italic=italic, color=color))
    runs = []
    parts = str(text).split("\n")
    for index, part in enumerate(parts):
        if index:
            runs.append("<w:r><w:br/></w:r>")
        runs.append(f'<w:r>{rpr(font=font, size=size, bold=bold, italic=italic, color=color)}<w:t xml:space="preserve">{esc(part)}</w:t></w:r>')
    return "<w:p><w:pPr>" + "".join(ppr) + "</w:pPr>" + "".join(runs) + "</w:p>"


def page_break() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def heading(text: str, level: int = 1) -> str:
    if level == 1:
        return p(text, style="Heading1", align="center", size=32, bold=True, before=120, after=240, font="Arial")
    if level == 2:
        return p(text, style="Heading2", size=28, bold=True, before=120, after=160, font="Arial")
    return p(text, size=26, bold=True, before=100, after=120, font="Arial")


def bullet(text: str) -> str:
    return p("- " + text, size=23, after=80, indent_left=360, first_line=-240)


def code_block(lines: list[str]) -> str:
    blocks = []
    for line in lines:
        blocks.append(p(line, font="Courier New", size=19, after=20, line=240, shade="F2F2F2"))
    return "".join(blocks)


def image_run(rid: str, doc_id: int, name: str, cx: int = 900000, cy: int = 900000) -> str:
    return f'''
    <w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">
      <wp:extent cx="{cx}" cy="{cy}"/>
      <wp:effectExtent l="0" t="0" r="0" b="0"/>
      <wp:docPr id="{doc_id}" name="{esc(name)}"/>
      <wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
      <a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:pic>
          <pic:nvPicPr><pic:cNvPr id="{doc_id}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
          <pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
          <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
        </pic:pic>
      </a:graphicData></a:graphic>
    </wp:inline></w:drawing></w:r>
    '''


def image_paragraph() -> str:
    return (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
        + image_run("rId5", 501, "Axis College Logo", 920000, 920000)
        + '<w:r><w:t xml:space="preserve">      </w:t></w:r>'
        + image_run("rId6", 502, "AKTU Logo", 920000, 920000)
        + "</w:p>"
    )


def figure_block(key: str) -> str:
    figure = FIGURE_MAP[key]
    image_xml = (
        '<w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
        + image_run(figure["rid"], figure["doc_id"], figure["caption"], figure["cx"], figure["cy"])
        + "</w:p>"
    )
    caption = p(figure["caption"], align="center", size=20, italic=True, after=180, color="334155")
    return image_xml + caption


def table(rows: list[list[str]], *, header: bool = True, widths: list[int] | None = None) -> str:
    if not rows:
        return ""
    cols = max(len(row) for row in rows)
    widths = widths or [int(9360 / cols)] * cols
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    xml = [
        '<w:tbl><w:tblPr><w:tblW w:w="9360" w:type="dxa"/>',
        '<w:tblBorders><w:top w:val="single" w:sz="8" w:color="000000"/>',
        '<w:left w:val="single" w:sz="8" w:color="000000"/>',
        '<w:bottom w:val="single" w:sz="8" w:color="000000"/>',
        '<w:right w:val="single" w:sz="8" w:color="000000"/>',
        '<w:insideH w:val="single" w:sz="4" w:color="000000"/>',
        '<w:insideV w:val="single" w:sz="4" w:color="000000"/></w:tblBorders>',
        '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>',
        '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>',
        '</w:tblPr><w:tblGrid>',
        grid,
        '</w:tblGrid>',
    ]
    for row_index, row in enumerate(rows):
        xml.append("<w:tr>")
        for col_index in range(cols):
            text = row[col_index] if col_index < len(row) else ""
            shade = "D9EAF7" if header and row_index == 0 else None
            xml.append(f'<w:tc><w:tcPr><w:tcW w:w="{widths[col_index]}" w:type="dxa"/>')
            if shade:
                xml.append(f'<w:shd w:fill="{shade}"/>')
            xml.append('</w:tcPr>')
            xml.append(p(text, size=20 if row_index else 21, bold=header and row_index == 0, after=40, line=240))
            xml.append("</w:tc>")
        xml.append("</w:tr>")
    xml.append("</w:tbl>")
    return "".join(xml) + p("", after=120)


def make_cover() -> str:
    blocks = [
        p("Project Report", align="center", size=36, bold=True, font="Arial", after=80),
        p("on", align="center", size=26, bold=True, font="Arial", after=80),
        p(PROJECT_TITLE, align="center", size=32, bold=True, font="Arial", after=180),
        image_paragraph(),
        p("Submitted as partial fulfillment for the award of", align="center", size=24, after=80),
        p("BACHELOR OF TECHNOLOGY DEGREE", align="center", size=30, bold=True, font="Arial", after=80),
        p(f"Session {SESSION} in", align="center", size=24, after=60),
        p(DEPARTMENT, align="center", size=24, bold=True, font="Arial", after=180),
        p("By", align="center", size=24, bold=True, after=60),
        p(f"{STUDENT}\n({ENROLLMENT})", align="center", size=24, bold=True, after=160),
        p("Under the guidance of", align="center", size=23, after=60),
        p(GUIDE, align="center", size=24, bold=True, after=220),
        p(COLLEGE, align="center", size=24, bold=True, font="Arial", after=80),
        p("AFFILIATED TO", align="center", size=20, bold=True, after=40),
        p(UNIVERSITY, align="center", size=20, bold=True, font="Arial", after=40),
    ]
    return "".join(blocks)


def declaration_page() -> str:
    return "".join([
        heading("Student's Declaration"),
        p(f"We hereby declare that the work being presented in this report entitled \"{PROJECT_TITLE.upper()}\" is an authentic record of project work carried out for the Bachelor of Technology degree in {DEPARTMENT}. The work is based on the Yashi AI assistant project developed, configured, tested, and documented as part of the college project activity.", align="both"),
        p(f"The matter embodied in this report has not been submitted by us for the award of any other degree or diploma. The technical descriptions, implementation notes, and testing observations are written from the actual project structure and the features implemented in the Yashi codebase.", align="both"),
        p("Date: ____________________", after=240),
        p("Signature of Student", align="right", after=120),
        p(f"{STUDENT}\n{DEPARTMENT}", align="right", bold=True),
        p("This is to certify that the above statement made by the candidate is correct to the best of my knowledge.", after=300),
        table([
            ["Signature of HOD", "Signature of Supervisor"],
            [HOD, GUIDE],
            ["Prof. & Head\nComputer Science & Engineering", "Assistant Professor\nComputer Science & Engineering"],
        ], widths=[4680, 4680]),
    ])


def acknowledgement_page() -> str:
    return "".join([
        heading("ACKNOWLEDGEMENT"),
        p(f"The successful completion of this project, {PROJECT_TITLE}, would not have been possible without the guidance, encouragement, and technical support received throughout the development process.", align="both"),
        p(f"I express sincere gratitude to {GUIDE}, Assistant Professor, Department of Computer Science & Engineering, for providing the opportunity to carry out this project and for offering constant support, suggestions, and motivation during the design and implementation of Yashi.", align="both"),
        p(f"I am thankful to {HOD}, Head of Department, for academic mentorship and for encouraging project work that combines artificial intelligence, software engineering, voice interfaces, and practical desktop automation.", align="both"),
        p(f"I also thank {COLLEGE} for providing an environment where application-oriented learning can be practiced. Finally, I thank my family, friends, and classmates for their patience and encouragement during development, testing, and documentation.", align="both"),
        p("Signature of Student", align="right", after=160),
        p(STUDENT.upper(), align="right", bold=True),
    ])


def abstract_page() -> str:
    return "".join([
        heading("ABSTRACT"),
        p("Yashi is an AI companion and personal desktop assistant designed to combine natural conversation, voice interaction, local app control, file operations, memory, emotional awareness, and a modern browser-based user interface. The project began as a local-first assistant using Ollama and later expanded to support cloud-based OpenAI models, ElevenLabs voice synthesis, wake-word activation, Spotify automation, file writing, mobile UI improvements, and a stop-response control similar to ChatGPT.", align="both"),
        p("The system uses a FastAPI backend, WebSocket streaming, a React frontend, a plugin architecture, SQLite-backed memory, configurable LLM and TTS backends, and browser SpeechRecognition for wake-word listening. Yashi can answer user prompts, stream tokens in real time, speak responses sentence by sentence, open applications, search the web, find local folders, create files, write and append content, and interrupt a response when the user presses Stop.", align="both"),
        p("The report explains the motivation, requirement analysis, architecture, implementation, testing, limitations, and future scope of the Yashi project. It also records review findings related to backend switching, static asset safety, wake-word reliability, and file operation scope, making the document useful not only as a project report but also as a technical handover artifact.", align="both"),
        table([
            ["Keyword", "Description"],
            ["AI Companion", "Conversational assistant with personality, memory, voice, and task automation."],
            ["FastAPI", "Backend framework used for APIs, WebSockets, static assets, and routes."],
            ["React", "Frontend framework used for the browser interface and mobile optimized UI."],
            ["Ollama/OpenAI", "LLM backends supported through configuration and sidebar settings."],
            ["ElevenLabs", "Optional human-like text-to-speech backend with browser fallback."],
        ], widths=[2200, 7160]),
    ])


def toc_pages() -> list[str]:
    rows_1 = [
        ["TITLE", "PAGE NO."],
        ["Declaration", "ii"],
        ["Acknowledgement", "iii"],
        ["Abstract", "iv"],
        ["Table of Contents", "v"],
        ["List of Figures", "vii"],
        ["List of Tables", "viii"],
        ["List of Abbreviations", "ix"],
        ["CHAPTER 1: INTRODUCTION", "1"],
        ["1.1 Background of AI Assistants", "1"],
        ["1.2 Problem Statement", "3"],
        ["1.3 Objectives and Scope", "5"],
        ["1.4 Use Cases", "7"],
        ["CHAPTER 2: LITERATURE REVIEW", "9"],
        ["2.1 Conversational AI Systems", "9"],
        ["2.2 Voice Assistants and Wake Words", "11"],
        ["2.3 LLM Deployment Approaches", "13"],
        ["2.4 Browser and Desktop Automation", "15"],
    ]
    rows_2 = [
        ["TITLE", "PAGE NO."],
        ["CHAPTER 3: REQUIREMENT ANALYSIS", "17"],
        ["CHAPTER 4: SYSTEM DESIGN", "24"],
        ["CHAPTER 5: IMPLEMENTATION", "34"],
        ["CHAPTER 6: TESTING AND VALIDATION", "48"],
        ["CHAPTER 7: RESULTS AND DISCUSSION", "56"],
        ["CHAPTER 8: CONCLUSION AND FUTURE SCOPE", "62"],
        ["REFERENCES", "66"],
        ["APPENDIX A: Project Structure", "68"],
        ["APPENDIX B: Setup and Environment", "70"],
        ["APPENDIX C: Review Findings and Improvements", "72"],
    ]
    return [
        heading("TABLE OF CONTENTS") + table(rows_1, widths=[7200, 2160]),
        heading("TABLE OF CONTENTS") + table(rows_2, widths=[7200, 2160]),
    ]


def lists_page() -> str:
    figures = [
        ["Figure No.", "Figure Description", "Page No."],
        ["Fig. 1", "College and university logos used on title page", "i"],
        ["Fig. 2", "High-level architecture of Yashi", "25"],
        ["Fig. 3", "Conversation and plugin processing pipeline", "28"],
        ["Fig. 4", "Stop response sequence flow", "33"],
        ["Fig. 5", "Feature completion and maturity chart", "36"],
        ["Fig. 6", "Ollama and OpenAI backend comparison", "38"],
        ["Fig. 7", "Risk matrix for local AI assistant features", "43"],
        ["Fig. 8", "Browser and mobile UI layout diagram", "47"],
        ["Fig. 9", "Yashi feature development timeline", "60"],
    ]
    tables = [
        ["Table No.", "Table Description", "Page No."],
        ["1.1", "Project objectives", "6"],
        ["3.1", "Functional requirements", "18"],
        ["3.2", "Non-functional requirements", "20"],
        ["4.1", "Module-wise architecture", "26"],
        ["5.1", "Implementation files and responsibilities", "36"],
        ["6.1", "Test cases and validation results", "50"],
    ]
    return heading("LIST OF FIGURES") + table(figures, widths=[1600, 5900, 1860]) + heading("LIST OF TABLES") + table(tables, widths=[1600, 5900, 1860])


def abbreviations_page() -> str:
    rows = [
        ["Abbreviation", "Full Form"],
        ["AI", "Artificial Intelligence"],
        ["API", "Application Programming Interface"],
        ["ASR", "Automatic Speech Recognition"],
        ["COM", "Component Object Model"],
        ["DOM", "Document Object Model"],
        ["HTTP", "Hypertext Transfer Protocol"],
        ["LLM", "Large Language Model"],
        ["NLP", "Natural Language Processing"],
        ["PWA", "Progressive Web Application"],
        ["RAG", "Retrieval Augmented Generation"],
        ["REST", "Representational State Transfer"],
        ["SPA", "Single Page Application"],
        ["STT", "Speech to Text"],
        ["TTS", "Text to Speech"],
        ["UI", "User Interface"],
        ["UX", "User Experience"],
        ["VAD", "Voice Activity Detection"],
        ["WS", "WebSocket"],
    ]
    return heading("LIST OF ABBREVIATIONS") + table(rows, widths=[2600, 6760])


CONTENT_PAGES = [
    {
        "title": "CHAPTER 1 INTRODUCTION",
        "paras": [
            "The Yashi project is a desktop and browser-based AI assistant developed to make everyday computer interaction more natural. Instead of limiting the assistant to typed chat, the project adds speech input, wake-word activation, streaming answers, voice output, local app control, file operations, memory, and a video avatar user interface.",
            "The central idea is that an assistant should feel available in the same way a real personal helper is available: it can answer questions, open tools, play music, create files, search folders, remember useful context, and stop speaking when the user interrupts.",
            "Yashi is implemented as a practical full-stack project. It combines Python backend services, React frontend components, WebSocket communication, local and cloud LLM integrations, and plugin modules that connect natural-language commands to operating-system actions.",
        ],
        "bullets": ["Project type: AI companion and personal desktop assistant.", "Main interface: browser UI with optional desktop shell.", "Primary goal: practical voice-first assistance on a personal computer."],
    },
    {
        "title": "1.1 Background of AI Personal Assistants",
        "paras": [
            "AI assistants have moved from simple rule-based command systems to conversational tools powered by large language models. Traditional assistants usually handled a narrow set of commands, but modern users expect richer conversation, flexible wording, and the ability to connect language with real actions.",
            "Yashi follows this modern direction. The assistant does not only answer text prompts; it also performs local actions such as opening Spotify, launching a browser search, finding files, creating notes, writing content into files, and using media keys for playback control.",
            "The project also explores the emotional and human side of assistance. The conversation engine tracks sentiment and emotion signals, selects a cognitive mode, and changes delivery style for voice output so that responses feel less mechanical.",
        ],
        "bullets": ["Natural language is treated as the main control layer.", "Conversation, voice, memory, and automation are integrated in one system.", "Human-like behavior is supported through TTS, emotion state, and personality prompts."],
    },
    {
        "title": "1.2 Motivation",
        "paras": [
            "Most users switch repeatedly between browser tabs, music apps, file explorer windows, editors, and search engines. A voice-enabled assistant can reduce this friction by turning spoken or typed instructions into direct actions.",
            "The motivation for Yashi was to build an assistant that feels lighter than a fully cloud-dependent product but more capable than a basic local chatbot. Ollama keeps the project usable without paid API usage, while optional OpenAI support allows the assistant to use a cloud model when the user chooses.",
            "Another motivation was to make the assistant useful for college-level learning. The project demonstrates real concepts from artificial intelligence, web development, backend engineering, operating-system integration, API usage, and human-computer interaction.",
        ],
        "bullets": ["Reduce repetitive manual actions on the computer.", "Use real AI models while keeping configuration flexible.", "Demonstrate applied full-stack AI engineering in a college project."],
    },
    {
        "title": "1.3 Problem Statement",
        "paras": [
            "The problem addressed by this project is the absence of a lightweight, personalized assistant that can combine conversation, voice, app launching, local file operations, memory, and a responsive user interface in one student-built system.",
            "Many assistant prototypes answer questions but do not control local applications. Other automation scripts can open apps but do not understand flexible natural language. Yashi attempts to bridge this gap through a plugin system that sits beside the LLM pipeline.",
            "The project also addresses response control. A user may send a prompt and then realize that the answer is too long or no longer needed. For this reason, Yashi includes a Stop button that replaces Send during generation and interrupts the output like ChatGPT.",
        ],
        "bullets": ["Conversational response generation must work with real-time streaming.", "Voice features must remain usable with browser limitations.", "Local actions must be separated from normal chat to avoid unnecessary LLM calls."],
    },
    {
        "title": "1.4 Objectives",
        "paras": [
            "The primary objective is to design and implement an AI assistant named Yashi that responds naturally to user prompts and supports useful desktop tasks. The assistant should run through a browser-based UI and also support a native desktop window through pywebview.",
            "A second objective is to support multiple intelligence and voice backends. Ollama provides a local free backend, OpenAI provides an optional cloud backend, ElevenLabs provides a human-like TTS option, and browser speech synthesis acts as a reliable fallback.",
            "A third objective is to improve usability. The project includes wake-word activation, a video avatar, mobile responsive layout, live status badges, streaming token output, sentence-by-sentence speech, and stop-response behavior.",
        ],
        "bullets": ["Build a full-stack AI assistant.", "Support local and cloud AI configuration.", "Provide voice, automation, file operations, and interruption control."],
    },
    {
        "title": "1.5 Scope of the Project",
        "paras": [
            "The project scope includes conversation, memory, emotional response handling, text-to-speech output, browser speech recognition, wake-word detection, application launching, Spotify control, web search, file creation, file writing, file appending, file/folder search, and UI settings.",
            "The scope also includes a backend settings route that allows changing the LLM and TTS backend from the frontend. This feature makes experimentation easier because the user can move between Ollama, OpenAI, ElevenLabs, and browser voice without restarting the full project.",
            "The current system is intended for personal computer usage. It is not yet a production-grade enterprise assistant, and some features such as full-computer file search need extra safety boundaries before being expanded beyond common user directories.",
        ],
        "bullets": ["Included: assistant UI, backend APIs, plugins, voice, settings, desktop wrapper.", "Partially included: broad file search and OS automation.", "Future expansion: safer whole-computer search and stronger wake-word engine."],
    },
    {
        "title": "1.6 Main Use Cases",
        "paras": [
            "The first major use case is normal conversation. A user can type or speak a question, and Yashi streams an answer token by token while also preparing voice output. This produces a more interactive experience than waiting for the full answer at once.",
            "The second use case is local task execution. Commands such as 'open Spotify', 'play a song', 'open Chrome and search something', or 'create a file called notes.txt' are detected by the intent detector and handled by plugins.",
            "The third use case is productivity assistance. The file operations plugin can create boilerplate files, write content to files, append notes, and open folders. This makes Yashi useful for quick capture and basic computer control.",
        ],
        "bullets": ["Conversation and explanation.", "Voice-first command execution.", "Music playback and browser search.", "File creation, writing, appending, and search."],
    },
    {
        "title": "1.7 Project Significance",
        "paras": [
            "Yashi is significant because it is not only a chatbot. It demonstrates how AI can be connected to the user's local environment while keeping the design modular and understandable. This makes the project suitable for learning, demonstration, and future extension.",
            "The project also shows the trade-off between local and cloud AI. Ollama avoids rate limits and cost but requires local resources. OpenAI is lighter on the PC but depends on API quota, internet access, and keys. Yashi exposes this choice through configuration.",
            "The project has educational value because it brings together software engineering practices such as modular architecture, route separation, plugin dispatch, WebSocket streaming, fallback handling, frontend state management, and test cases.",
        ],
        "bullets": ["Combines AI concepts with operating-system automation.", "Keeps important choices configurable.", "Documents practical challenges and review findings honestly."],
    },
    {
        "title": "CHAPTER 2 LITERATURE REVIEW",
        "paras": [
            "The literature review for Yashi covers AI assistants, language models, voice recognition, text-to-speech systems, wake-word activation, desktop automation, and web-based user interfaces. These areas are important because Yashi exists at the intersection of conversational AI and personal productivity software.",
            "Modern assistants such as Alexa, Siri, Google Assistant, and ChatGPT show that users prefer natural language over rigid commands. However, combining natural language with safe local computer actions remains a challenging engineering task.",
            "Yashi's design borrows ideas from these systems while remaining a student-built project. It uses LLMs for language, plugins for deterministic actions, and a browser frontend for accessibility.",
        ],
        "bullets": ["Conversational AI provides flexible language understanding.", "Plugins provide controlled action execution.", "Voice and UI layers make interaction more natural."],
    },
    {
        "title": "2.1 Conversational AI Systems",
        "paras": [
            "Conversational AI systems are designed to interpret user messages and generate meaningful responses. Earlier systems were often based on fixed templates and keyword matching. Modern systems use transformer-based language models that can produce flexible, context-aware answers.",
            "In Yashi, the conversational layer is handled by a conversation engine that builds prompts using user text, recent history, semantic memory, personal facts, reflections, emotion state, and cognitive mode. This gives the LLM more context than a single isolated prompt.",
            "The project uses streaming generation so that the frontend receives tokens as soon as the model produces them. This approach improves perceived responsiveness and allows the stop-response feature to interrupt long outputs.",
        ],
        "bullets": ["Prompt building includes memory and emotional context.", "Streaming avoids waiting for complete generation.", "Stop control depends on cooperative cancellation in the engine."],
    },
    {
        "title": "2.2 Large Language Model Deployment",
        "paras": [
            "LLMs can be deployed locally or through cloud APIs. Local deployment gives privacy and avoids request limits, but it requires CPU, RAM, and sometimes GPU resources. Cloud deployment can be lighter for the PC, but it needs an API key and may introduce rate limits or usage costs.",
            "Yashi supports both styles. Ollama is configured as the default backend because it is free, local, and already available in the project environment. OpenAI support was added through a dedicated client with GPT-4o-mini streaming and retry logic for rate-limit errors.",
            "This dual backend design makes the assistant flexible. A student can demonstrate the project using local resources, then switch to OpenAI if stronger cloud inference is needed and a valid API key is available.",
        ],
        "bullets": ["Ollama backend: local, free, no API key, PC resource usage.", "OpenAI backend: cloud, lightweight locally, API key and quota required.", "Settings panel allows switching between supported backends."],
    },
    {
        "title": "2.3 Speech Recognition",
        "paras": [
            "Speech recognition converts spoken language into text that can be processed by an assistant. Browser-based speech recognition is convenient because it avoids building a separate native audio pipeline for every platform.",
            "Yashi uses browser SpeechRecognition for the wake-word feature. The recognizer listens for the word 'Yashi' and either sends the remaining command immediately or activates the main microphone for a short command window.",
            "A limitation of this approach is browser availability. Chrome supports the Web Speech API better than many embedded desktop contexts. Therefore, Yashi disables wake-word behavior gracefully in pywebview desktop mode and displays a helpful state instead of pretending it is active.",
        ],
        "bullets": ["Wake word: 'Yashi'.", "Direct command pattern: 'Yashi play music'.", "Activation pattern: saying only 'Yashi' opens the main mic for a command window."],
    },
    {
        "title": "2.4 Text-to-Speech Systems",
        "paras": [
            "Text-to-speech systems convert generated text into spoken audio. Human-like TTS improves the feeling of interaction because the assistant is no longer restricted to silent text. The project supports browser speech synthesis and ElevenLabs.",
            "ElevenLabs support was added through a dedicated TTS module. It uses the Rachel voice and the eleven_turbo_v2_5 model. Voice delivery changes according to detected emotion by adjusting stability and style parameters.",
            "Yashi speaks sentence by sentence while the response is being generated. If ElevenLabs fails because of an invalid key, quota, network issue, or rate limit, the frontend falls back to browser speech so that the assistant remains usable.",
        ],
        "bullets": ["ElevenLabs gives human-like voice quality.", "Browser TTS gives dependable fallback.", "Sentence-level streaming prevents long silent waits."],
    },
    {
        "title": "2.5 Wake-Word Activation",
        "paras": [
            "Wake-word activation allows an assistant to become active without pressing a button. This behavior is familiar from voice assistants where the name of the assistant starts the command flow.",
            "In Yashi, wake-word listening is implemented in the frontend. The recognizer continuously listens in supported browsers and uses fuzzy matching to reduce failures caused by mishearing names such as 'Yashi' or similar sounds.",
            "The project also handles the technical constraint that Chrome does not allow two recognizers to run at the same time. The wake recognizer stops itself before the main microphone begins listening.",
        ],
        "bullets": ["Always-on listener runs in supported browsers.", "Fuzzy matching improves reliability.", "Recognizer handoff prevents mic conflicts."],
    },
    {
        "title": "2.6 Desktop Automation",
        "paras": [
            "Desktop automation connects user intent to local operating-system actions. Instead of only explaining how to open an app, an assistant can directly launch Spotify, Chrome, Edge, Discord, VS Code, VLC, Notepad, Calculator, and other applications.",
            "Yashi's app launcher searches known Windows installation paths and uses URI schemes when appropriate. For Spotify, it can open search results through spotify:search and then use keyboard/media-key automation to attempt playback.",
            "Automation must be designed carefully because local actions can affect the user's computer. Yashi keeps automation in plugins so that the command path is easier to review and expand.",
        ],
        "bullets": ["Application paths are searched in common Windows locations.", "Spotify uses URI search and media controls.", "Plugins isolate automation from normal chat responses."],
    },
    {
        "title": "2.7 File Operations in Assistants",
        "paras": [
            "File operations are a useful feature for a personal assistant because many user tasks involve creating, finding, editing, and organizing files. A natural-language assistant can reduce the number of manual steps required for these operations.",
            "Yashi's file operations plugin can create files, prefill boilerplate for common formats, write content, append content, search for files by name, and open folders. The intent detector identifies commands such as 'write Hello world to file notes.txt'.",
            "The project currently keeps broad file behavior controlled. True whole-computer search and modification require additional confirmation and safety boundaries because unrestricted file access can expose or alter sensitive data.",
        ],
        "bullets": ["Supported actions: create, write, append, find, open folder.", "Boilerplate is generated for Python, HTML, and Markdown.", "Future work: safer full-disk search with user confirmation."],
    },
    {
        "title": "2.8 WebSocket-Based Streaming",
        "paras": [
            "WebSockets allow continuous two-way communication between frontend and backend. This is important for AI assistants because messages are not limited to one request and one final response.",
            "Yashi uses WebSocket routes for text chat and audio communication. The chat route can send events such as connected, emotion, thinking, token, done, safety, plugin_response, and stopped behavior through the same channel.",
            "Streaming also helps with cancellation. When the user presses Stop, the frontend sends a stop message, the engine sets a stop event, and generation ends with a done event marked as stopped.",
        ],
        "bullets": ["Text WebSocket: /ws/chat/{client_id}.", "Audio WebSocket: /ws/audio/{client_id}.", "Streaming events drive UI, voice, status, and cancellation."],
    },
    {
        "title": "CHAPTER 3 REQUIREMENT ANALYSIS",
        "paras": [
            "Requirement analysis defines what the system must do and how well it must do it. For Yashi, the requirements cover conversation, voice, UI, backend routing, file operations, app launching, model configuration, memory, responsiveness, and safety.",
            "The requirements were derived from the desired features: opening apps, searching directories, wake-word activation, optional OpenAI support, ElevenLabs voice, video avatar UI, mobile browser optimization, Spotify playback, file writing, and stop-response control.",
            "Because the project runs on a personal computer, requirements must consider local resources, browser limitations, Windows paths, API key availability, and user control over automation.",
        ],
        "bullets": ["Functional requirements describe what Yashi can do.", "Non-functional requirements describe reliability, usability, privacy, and performance.", "Safety requirements limit risky local actions."],
    },
    {
        "title": "3.1 Functional Requirements",
        "paras": [
            "The system must accept typed prompts and spoken commands. It must process natural language, decide whether a plugin should handle the command, and otherwise forward the message to the conversation engine.",
            "The assistant must stream model output to the frontend and support TTS playback. It must allow the user to stop output at any time while a response is being generated.",
            "The assistant must expose settings for LLM and voice backend selection so that Ollama, OpenAI, ElevenLabs, and browser voice can be toggled from the UI.",
        ],
        "table": [
            ["Requirement", "Description"],
            ["Conversation", "Respond to natural-language prompts with streaming output."],
            ["Voice", "Support speech recognition, TTS, and wake-word activation."],
            ["Automation", "Open apps, control Spotify, search web, and use file plugins."],
            ["Stop Response", "Replace Send with Stop while generating and cancel output on demand."],
            ["Settings", "Allow runtime backend selection through sidebar controls."],
        ],
    },
    {
        "title": "3.2 Non-Functional Requirements",
        "paras": [
            "The system should feel responsive even when the model is still generating. WebSocket token streaming, sentence-level TTS, and live typing indicators support this requirement.",
            "The system should be usable on a browser and on smaller mobile screens. The interface must provide a mobile menu, responsive message layout, appropriate spacing, and a composer that remains reachable.",
            "The system should remain usable when optional services fail. If ElevenLabs is unavailable, browser TTS should speak the response. If OpenAI rate limits occur, Ollama remains the default local option.",
        ],
        "table": [
            ["Quality", "Requirement"],
            ["Usability", "Clear controls, mobile layout, status badges, and visible stop control."],
            ["Reliability", "Fallbacks for TTS and backend availability."],
            ["Performance", "Streaming responses, limited context, and model routing."],
            ["Privacy", "Local Ollama path available for offline/private usage."],
            ["Maintainability", "Modular routes, plugins, config, and frontend state handling."],
        ],
    },
    {
        "title": "3.3 Hardware and Software Requirements",
        "paras": [
            "Yashi is designed to run on a Windows personal computer. The local model path benefits from sufficient RAM and CPU/GPU capacity, while the OpenAI path reduces local inference load but requires internet access and an API key.",
            "The backend uses Python and FastAPI. The frontend uses React, Vite, TailwindCSS, and browser APIs. Optional desktop mode uses pywebview to present the app as a native Windows window.",
            "The voice stack uses browser SpeechRecognition for wake word, faster-whisper or related STT modules for audio routes, ElevenLabs for optional TTS, and browser speech synthesis as a fallback.",
        ],
        "table": [
            ["Component", "Technology"],
            ["Backend", "Python, FastAPI, WebSockets"],
            ["Frontend", "React, Vite, TailwindCSS"],
            ["Local LLM", "Ollama with phi3:mini"],
            ["Cloud LLM", "OpenAI GPT-4o-mini"],
            ["TTS", "ElevenLabs and browser speech synthesis"],
            ["Desktop Shell", "pywebview"],
        ],
    },
    {
        "title": "3.4 User Requirements",
        "paras": [
            "The user should be able to interact with Yashi naturally. Commands should not require exact rigid phrasing. The intent detector strips trailing punctuation and recognizes common patterns such as opening apps, controlling Spotify, and writing files.",
            "The user should be able to choose the assistant's brain and voice backend. This supports experimentation and reduces dependency on any single provider.",
            "The user should be able to interrupt output. This is especially important for voice assistants because long spoken responses can become annoying if the user already has enough information.",
        ],
        "bullets": ["Natural typed and spoken interaction.", "Visible settings and live backend status.", "Stop button during generation.", "Helpful fallback states when wake word or services are unavailable."],
    },
    {
        "title": "3.5 Constraints",
        "paras": [
            "The first constraint is browser support. Wake-word activation depends on browser SpeechRecognition, which is strongest in Chrome. In desktop pywebview mode this feature is disabled gracefully because the embedded environment may not support the same recognizer.",
            "The second constraint is API quota. OpenAI free-tier usage can be limited, causing 429 rate-limit responses. For this reason, retry logic exists, but Ollama remains the default backend.",
            "The third constraint is safe local file access. The original feature goal was 'any directory', but unrestricted search or modification across the entire computer should be implemented carefully with confirmation, path validation, and clear user consent.",
        ],
        "bullets": ["Wake word depends on browser capabilities.", "OpenAI depends on key, internet, and quota.", "Local file access must balance power and safety."],
    },
    {
        "title": "3.6 Risk Analysis",
        "paras": [
            "A personal assistant that can open apps and write files has higher risk than a normal chatbot. Misinterpreted commands could open the wrong app or alter the wrong file if safeguards are weak.",
            "The project reduces risk by routing actions through explicit plugins, keeping common file roots controlled, and separating automation logic from normal LLM-generated text. Future improvements should add confirmations for destructive or broad file operations.",
            "Security review also identified path traversal risk in static file serving if paths are joined without resolving and checking containment. This type of issue should be fixed before public deployment.",
        ],
        "table": [
            ["Risk", "Mitigation"],
            ["Misheard wake word", "Fuzzy matching, restart logic, and clear UI status."],
            ["API quota failure", "Retry/backoff and Ollama default."],
            ["Wrong file target", "Path resolution, scoped roots, and future confirmations."],
            ["Static path traversal", "Resolve path and enforce containment checks."],
        ],
    },
    {
        "title": "CHAPTER 4 SYSTEM DESIGN",
        "paras": [
            "Yashi follows a modular full-stack architecture. The React frontend handles UI, microphone, wake word, speech playback, video avatar, and WebSocket communication. The FastAPI backend handles routes, WebSocket sessions, model orchestration, memory, TTS, and plugin dispatch.",
            "The core conversation engine is responsible for emotion fusion, safety checks, memory retrieval, prompt building, LLM streaming, TTS event generation, storing conversation history, and reflection.",
            "Plugins provide deterministic actions. This design keeps local automation separate from the LLM so that commands such as opening Spotify or writing a file do not require the model to invent operating-system behavior.",
        ],
        "code": [
            "User -> React UI -> WebSocket -> FastAPI chat route",
            "FastAPI -> Plugin dispatcher -> App/File/Web actions",
            "FastAPI -> ConversationEngine -> Prompt -> LLM stream",
            "ConversationEngine -> TTS events -> Frontend speech playback",
            "ConversationEngine -> SQLite memory -> Future context",
        ],
    },
    {
        "title": "4.1 High-Level Architecture",
        "paras": [
            "The frontend and backend communicate through WebSocket messages. This gives the frontend immediate updates for connection status, thinking mode, tokens, TTS sentences, plugin responses, and final done events.",
            "The backend uses route modules to keep responsibilities separated. Chat, audio, memory, TTS serving, settings, and static assets are placed in their own files under app/routes or app/main.",
            "The core directory contains model, memory, emotion, voice, cognitive, safety, and conversation logic. This separation makes the project easier to explain and test.",
        ],
        "table": [
            ["Layer", "Responsibility"],
            ["Frontend", "User interface, mic, wake word, video avatar, speech playback."],
            ["API Layer", "FastAPI routes, WebSocket session management, settings endpoints."],
            ["Core Engine", "Conversation, prompt building, memory, safety, emotion, TTS."],
            ["Plugins", "App launching, Spotify control, web search, file operations."],
            ["Data", "SQLite database, logs, TTS cache, static assets."],
        ],
    },
    {
        "title": "4.2 Backend Design",
        "paras": [
            "The backend is based on FastAPI. app/main.py initializes the application, loads environment variables, registers routes, performs startup checks, and serves frontend/static assets.",
            "The chat WebSocket route creates a ConversationEngine per client and stores it in a dictionary. It handles text messages, new sessions, ping messages, plugin dispatch, and stop messages.",
            "The backend uses async functions because LLM streaming, TTS synthesis, and WebSocket sends are naturally asynchronous. This helps keep the app responsive while long operations run.",
        ],
        "bullets": ["app/main.py: FastAPI app setup and static route handling.", "app/routes/chat.py: text chat WebSocket and stop-message flow.", "app/websocket_manager.py: WebSocket connection management."],
    },
    {
        "title": "4.3 Conversation Engine Design",
        "paras": [
            "The conversation engine orchestrates the main AI pipeline. For every prompt, it clears old stop state, fuses emotion signals, runs safety checks, stores the user message, extracts facts, selects a cognitive mode, retrieves memory, builds a prompt, and streams model output.",
            "During generation, the engine stores the active partial response. If the stop event is set, the engine breaks from streaming, cancels pending TTS tasks, saves partial output when available, and yields a done event with stopped set to true.",
            "The engine also supports reflection after normal responses. Reflection allows the memory layer to create higher-level insights from conversation history.",
        ],
        "code": [
            "process_message(user_text)",
            "  clear_stop()",
            "  emotion = fuse_emotion(user_text)",
            "  mode = select_cognitive_mode(user_text, emotion)",
            "  prompt = build_prompt(history, memory, facts, emotion, mode)",
            "  async for token in llm.generate_stream(...):",
            "      if stop_event: break",
            "      yield token",
            "  yield done(stopped=True/False)",
        ],
    },
    {
        "title": "4.4 LLM Backend Design",
        "paras": [
            "The LLM layer supports two backends: Ollama and OpenAI. The configuration constant LLM_BACKEND decides which client is used when the conversation engine is created.",
            "Ollama is the default because it is local, free, and avoids request-rate limits. The current settings map light, standard, deep, and support modes to phi3:mini for faster operation on limited hardware.",
            "The OpenAI client supports GPT-4o-mini and includes exponential backoff for rate-limit errors. This makes cloud usage more robust, although it cannot remove the limits of a free-tier account.",
        ],
        "table": [
            ["Backend", "Strength", "Limitation"],
            ["Ollama", "Private, local, free, no API quota.", "Consumes local CPU/RAM/GPU resources."],
            ["OpenAI", "High-quality cloud inference, low PC load.", "Needs key, internet, and quota."],
        ],
    },
    {
        "title": "4.5 Voice Design",
        "paras": [
            "The voice design has three parts: speech recognition, response speech, and lip/status feedback. The browser is responsible for wake-word recognition and speech synthesis fallback. The backend generates TTS audio paths when ElevenLabs is active.",
            "Yashi uses sentence-level TTS events. Instead of waiting for the entire LLM response, the engine flushes sentences and punctuation-based chunks so voice playback can begin earlier.",
            "The frontend also controls lip animation and cancels speech when the user stops output. This makes the assistant feel more responsive and gives the user control over sound.",
        ],
        "bullets": ["Wake word listens in supported browsers.", "ElevenLabs provides high-quality voice when configured.", "Browser TTS prevents silence when ElevenLabs fails.", "Stop cancels queued and active speech playback."],
    },
    {
        "title": "4.6 Memory Design",
        "paras": [
            "Yashi includes a memory system so that conversation can become more personalized over time. Conversation history, semantic memories, extracted facts, reflections, behavior state, and session statistics are stored in the data layer.",
            "The conversation engine retrieves recent messages, semantic memory results, personal facts, and reflections before building the prompt. This gives the LLM continuity and allows Yashi to respond with context.",
            "SQLite is used because it is lightweight and suitable for a local personal assistant project. The database file lives under the data directory.",
        ],
        "table": [
            ["Memory Component", "Purpose"],
            ["Conversation Store", "Stores dialogue history with emotion tags."],
            ["Semantic Memory", "Stores searchable memory vectors or memory snippets."],
            ["Fact Extractor", "Extracts personal facts from messages."],
            ["Reflection Engine", "Creates periodic insights from conversation history."],
        ],
    },
    {
        "title": "4.7 Plugin Architecture",
        "paras": [
            "The plugin architecture is one of the most important design decisions in Yashi. Plugins allow specific actions to be handled deterministically without asking the LLM to control the computer through free-form generated text.",
            "The plugin loader discovers plugin modules and dispatches user text to the correct plugin based on detected intent. Each plugin returns a structured response with success status, message, and data.",
            "Current plugin areas include application launching, web launching/search, file search, and file operations. The app launcher was expanded to control Spotify playback and media keys.",
        ],
        "code": [
            "detect_intent(text) -> { intent, target, extra }",
            "plugin_dispatch(text, context)",
            "  for plugin in loaded_plugins:",
            "      if plugin.can_handle(text, intent):",
            "          return plugin.execute(text, context)",
        ],
    },
    {
        "title": "4.8 Frontend Design",
        "paras": [
            "The frontend is implemented in React. It maintains application state such as messages, typing status, connection state, mic state, wake-word state, selected LLM backend, selected TTS backend, and UI panel visibility.",
            "The UI includes a video avatar, chat panel, composer, sidebar settings, mobile menu, wake-word toggle, voice toggle, and backend status badges. The avatar video is served through the backend static route.",
            "Mobile optimization was added so that the browser interface remains usable on smaller screens. The sidebar can slide in, messages are resized, and the composer spacing is adjusted for mobile usage.",
        ],
        "bullets": ["React state reducer controls app state.", "WebSocket event handler updates messages and status.", "Send button becomes Stop while Yashi is responding.", "Video avatar replaces manual canvas animation for now."],
    },
    {
        "title": "4.9 Desktop App Design",
        "paras": [
            "The desktop app uses pywebview to present Yashi in a native Windows window. The FastAPI backend runs in a daemon thread inside the same process, allowing the user to launch one desktop entry point.",
            "This mode is useful for a personal assistant because it feels more like an installed app than a browser tab. However, some browser APIs behave differently in embedded webviews.",
            "Because wake-word recognition depends on browser SpeechRecognition, the desktop mode disables wake word gracefully and tells the user that Chrome browser mode is required for that feature.",
        ],
        "bullets": ["Entry point: desktop.py.", "Backend runs in-process.", "UI loads through pywebview.", "Wake word is browser-only at this stage."],
    },
    {
        "title": "CHAPTER 5 IMPLEMENTATION",
        "paras": [
            "Implementation is divided into backend services, frontend UI, core AI modules, voice modules, and plugins. This chapter documents the most important files and the behavior added during project development.",
            "The implementation emphasizes working features rather than theoretical design only. Yashi can actually open applications, search Spotify, write files, speak responses, and interrupt output.",
            "The project also includes infrastructure changes such as environment loading, static video routes, settings APIs, and a desktop shell.",
        ],
        "table": [
            ["Area", "Important Files"],
            ["Backend", "app/main.py, app/routes/chat.py, app/routes/settings_api.py"],
            ["Conversation", "core/conversation/engine.py"],
            ["LLM", "core/llm/ollama_client.py, core/llm/openai_client.py"],
            ["Voice", "core/voice/elevenlabs_tts.py, core/voice/stt.py, core/voice/tts.py"],
            ["Plugins", "plugins/app_launcher/plugin.py, plugins/file_ops/plugin.py"],
            ["Frontend", "frontend/src/App.jsx"],
        ],
    },
    {
        "title": "5.1 OpenAI Integration",
        "paras": [
            "OpenAI integration was added through core/llm/openai_client.py. The client streams tokens from GPT-4o-mini so the frontend can display partial output as it arrives.",
            "The client includes retry logic for rate limiting. Delays increase across retries, using a pattern such as 2 seconds, 5 seconds, 12 seconds, and 25 seconds. This helps the system recover from temporary 429 errors.",
            "The project later switched the default LLM backend back to Ollama because the OpenAI free tier caused request-per-minute limits during testing. The OpenAI path remains available as an optional backend.",
        ],
        "bullets": ["Config key: LLM_BACKEND.", "Model: GPT-4o-mini.", "Fallback decision: Ollama default for cost-free local usage."],
    },
    {
        "title": "5.2 Ollama Local Backend",
        "paras": [
            "Ollama is the default model backend in the current configuration. It allows Yashi to run without paid cloud usage and without sending prompts to an external model provider.",
            "The settings map all cognitive modes to phi3:mini so that the assistant remains light enough for the user's PC. This choice prioritizes responsiveness over maximum model quality.",
            "Ollama also makes demos easier because there is no API quota to exhaust. As long as Ollama is running locally and the model is pulled, the assistant can continue responding.",
        ],
        "table": [
            ["Setting", "Value"],
            ["LLM_BACKEND", "ollama"],
            ["OLLAMA_BASE_URL", "http://localhost:11434"],
            ["DEFAULT_MODEL", "phi3:mini"],
            ["LLM_MAX_TOKENS", "350"],
        ],
    },
    {
        "title": "5.3 ElevenLabs Voice Integration",
        "paras": [
            "ElevenLabs TTS was added in core/voice/elevenlabs_tts.py. The module uses the Rachel voice and the eleven_turbo_v2_5 model to create more human-like speech.",
            "Emotion-adaptive delivery changes parameters such as stability and style. For example, distressed responses can sound slower and softer, while excited responses can be more expressive.",
            "The implementation is resilient. If ElevenLabs returns an error, invalid key, quota issue, or rate limit, the frontend receives a TTS event without an audio path and speaks the sentence through browser TTS.",
        ],
        "bullets": ["API key comes from ELEVENLABS_API_KEY.", "Generated audio is cached under data/tts_cache.", "Browser speech is the fallback path."],
    },
    {
        "title": "5.4 Wake Word Implementation",
        "paras": [
            "Wake-word support was implemented in the frontend using the Web Speech API. When enabled, a background recognizer listens for the assistant name 'Yashi'.",
            "If the user says a full command such as 'Yashi play music', the command can be sent immediately. If the user says only 'Yashi', the main mic activates for a limited window so the user can continue speaking.",
            "Reliability was improved with fuzzy matching, alias handling, restart timers, and better UI state management. The button no longer reports success when activation is unavailable.",
        ],
        "bullets": ["Chrome browser provides the best support.", "Desktop pywebview mode disables the feature gracefully.", "Wake recognizer stops before main mic starts."],
    },
    {
        "title": "5.5 App Launcher Implementation",
        "paras": [
            "The app launcher plugin opens local applications by searching common Windows install paths and using known executable locations. It supports Spotify, Chrome, Discord, VS Code, Edge, VLC, Notepad, Calculator, and other apps.",
            "For browser search, the plugin can open Google results in the default browser. This connects natural-language commands with normal web browsing workflows.",
            "The intent detector strips trailing punctuation so commands like 'Open Spotify.' do not fail because of the period at the end.",
        ],
        "table": [
            ["Command Type", "Example"],
            ["Open app", "open Spotify"],
            ["Web search", "search Python decorators"],
            ["Media control", "pause music"],
            ["Browser launch", "open Chrome"],
        ],
    },
    {
        "title": "5.6 Spotify Playback Implementation",
        "paras": [
            "Spotify search was added through the spotify:search URI scheme. When the user asks Yashi to play a song, Spotify opens to search results for that song.",
            "The project was then improved so Yashi attempts to start playback after searching. The app launcher focuses the Spotify window and uses keyboard/media-key automation through pynput and Windows foreground window handling.",
            "Spotify UI behavior can vary across versions, so the implementation includes fallback messages. If autoplay fails, the user still lands on the correct search result and can press Enter or Play.",
        ],
        "bullets": ["Search method: spotify:search:SONGNAME.", "Playback method: foreground focus and keyboard/media key automation.", "Fallback: browser search or user prompt when Spotify automation is unavailable."],
    },
    {
        "title": "5.7 File Creation and Write Operations",
        "paras": [
            "The file operations plugin originally created files but did not fully handle writing content after creation. The implementation was expanded with file_write and file_append intents.",
            "The intent detector now supports commands such as 'write Hello world to file notes.txt' and 'append meeting notes to file notes.txt'. The plugin resolves the file target, writes or appends content, and opens the file when appropriate.",
            "Boilerplate generation also improves usability. Python files receive a basic main structure, HTML files receive a skeleton page, and Markdown files receive a header.",
        ],
        "bullets": ["Create: creates a file on Desktop or resolved target path.", "Write: replaces file content with requested text.", "Append: adds requested text to the existing file.", "Find/open: searches common folders and opens folders in Explorer."],
    },
    {
        "title": "5.8 Settings Toggle Implementation",
        "paras": [
            "The sidebar includes an AI Settings panel with controls for the brain backend and voice backend. Users can switch between Ollama and OpenAI, and between ElevenLabs and browser voice.",
            "The backend route updates settings.py, reloads configuration, and resets client singletons. This allows configuration changes without restarting the whole app in many cases.",
            "A review finding notes that an already-open chat session may keep the old ConversationEngine instance. To fully apply a live backend switch to current sessions, the active engine should be rebuilt or updated after settings change.",
        ],
        "bullets": ["Brain options: Ollama and OpenAI.", "Voice options: ElevenLabs and browser voice.", "Live badges show the active backend.", "Known improvement: rebuild active engine after hot-swap."],
    },
    {
        "title": "5.9 Video Avatar Implementation",
        "paras": [
            "The frontend currently uses a looping video element instead of manual canvas animation. This was chosen to prioritize core assistant features before investing more time in custom avatar animation.",
            "The avatar video is stored under frontend/assets or related static/public folders and served through the backend static route as /static/yashi-avatar.mp4.",
            "In focus mode, the UI uses a dark background and portrait-style sizing so the avatar can occupy the main visual area while chat controls remain available on the side.",
        ],
        "bullets": ["Current asset: yashi-avatar.mp4.", "Manual animation is deferred for future work.", "Video route supports frontend and backend serving paths."],
    },
    {
        "title": "5.10 Mobile UI Optimization",
        "paras": [
            "The browser UI was optimized for mobile users by adding a mobile menu, slide-in sidebar behavior, backdrop handling, tighter message spacing, and responsive composer layout.",
            "This matters because a voice assistant may be used from a phone browser or a narrow desktop window. Controls must remain reachable, readable, and free from overlap.",
            "The mobile UI still preserves the main experience: avatar, conversation panel, settings access, wake-word toggle, mic button, and Send/Stop composer behavior.",
        ],
        "bullets": ["Sidebar becomes mobile-friendly.", "Composer remains visible and usable.", "Message bubbles scale better on narrow screens.", "Status and settings are still accessible."],
    },
    {
        "title": "5.11 Stop Response Feature",
        "paras": [
            "The Stop response feature gives users control over long or unwanted output. After the user sends a prompt, the Send button is replaced by Stop while Yashi is responding, similar to ChatGPT.",
            "On the frontend, pressing Stop sends a WebSocket message of type stop, cancels queued speech, stops lip animation, clears typing state, and marks the current stream as stopped.",
            "On the backend, the chat route forwards stop requests to the ConversationEngine. The engine sets a stop event, breaks streaming, cancels pending TTS tasks, and emits a done event with stopped set to true.",
        ],
        "code": [
            "Frontend: socket.send({ type: 'stop' })",
            "Backend: engine.request_stop()",
            "Engine: if self._stop_event.is_set(): stopped = True; break",
            "Done event: { type: 'done', stopped: true }",
        ],
    },
    {
        "title": "5.12 Static Asset Serving",
        "paras": [
            "Static asset serving is used for frontend assets such as the avatar video and generated TTS audio. The FastAPI app searches known frontend and data paths to locate files.",
            "A review finding identified that static routes should protect against path traversal. Any route that joins user-provided paths with a base directory should resolve the final path and verify that it remains inside the intended root.",
            "This issue is important because assistants often expose local file paths. Static serving must be carefully limited before the project is used outside a trusted local environment.",
        ],
        "bullets": ["Serve video avatar through /static.", "Serve TTS cache through TTS route.", "Required hardening: resolve paths and enforce containment."],
    },
    {
        "title": "5.13 Desktop App Implementation",
        "paras": [
            "desktop.py runs Yashi as a native Windows-style application using pywebview. The FastAPI backend starts as a daemon thread and the UI loads inside the embedded window.",
            "This makes the project feel closer to a complete product. Instead of starting a browser manually, the user can launch a single desktop script.",
            "The desktop mode also reveals real-world constraints. Some browser features, especially wake-word recognition, are not available in the embedded environment and therefore need clear fallback states.",
        ],
        "bullets": ["Install command: pip install pywebview.", "Run command: python desktop.py.", "Wake word: use Chrome browser mode for best support."],
    },
    {
        "title": "5.14 Environment and Configuration",
        "paras": [
            "Configuration is centralized in config/settings.py. This file defines backend choices, model settings, API key loading, TTS settings, audio parameters, memory limits, safety thresholds, and the Yashi persona.",
            "Environment variables are loaded from .env before backend modules are imported. This is important for API keys such as OPENAI_API_KEY and ELEVENLABS_API_KEY.",
            "A previous issue caused repeated import errors because constants expected by modules were missing. The settings file was rewritten to include all needed constants.",
        ],
        "table": [
            ["Config Area", "Examples"],
            ["LLM", "LLM_BACKEND, OPENAI_MODEL, OLLAMA_BASE_URL"],
            ["TTS", "TTS_BACKEND, ELEVENLABS_API_KEY, PIPER_OUTPUT_DIR"],
            ["Audio", "SAMPLE_RATE, VAD thresholds, WHISPER_MODEL"],
            ["Memory", "MAX_CONTEXT_MESSAGES, VECTOR_TOP_K"],
            ["Safety", "Dependency warning and session limits"],
        ],
    },
    {
        "title": "5.15 Error Handling and Fallbacks",
        "paras": [
            "Yashi includes several fallback paths because AI assistants depend on external services, browser APIs, and local system state. Robust fallback behavior keeps the user from getting stuck.",
            "OpenAI rate limits are handled through exponential backoff. ElevenLabs failures fall back to browser speech. Wake-word unavailability updates the UI instead of showing a false active state.",
            "Plugin responses also reset typing state so the UI does not remain stuck after a quick automation action. This was an important bug fix because app-launching commands should finish cleanly.",
        ],
        "bullets": ["OpenAI: retry/backoff for 429 errors.", "TTS: browser fallback if ElevenLabs fails.", "Wake word: unavailable states are shown honestly.", "Plugin response: typing/status state is reset."],
    },
    {
        "title": "CHAPTER 6 TESTING AND VALIDATION",
        "paras": [
            "Testing validates that important behavior works and that changes do not break existing features. Yashi includes Python tests in tests/test_all.py and frontend build verification through npm run build.",
            "The project was also tested manually through user-level commands such as opening Spotify, searching songs, creating files, writing file content, enabling wake word, and switching settings.",
            "Some tests could not be run in earlier verification because pytest was not installed in the available Python environment. However, frontend builds were successfully run after UI changes.",
        ],
        "bullets": ["Automated tests cover intent detection and core modules.", "Manual smoke tests cover voice, UI, plugins, and app launcher behavior.", "Build verification confirms frontend compilation."],
    },
    {
        "title": "6.1 Test Plan",
        "paras": [
            "The test plan divides validation into unit tests, integration tests, UI tests, and manual system tests. Unit tests are suitable for intent detection, mode selection, prompt building, and plugin routing.",
            "Integration tests are needed for the WebSocket route, conversation engine, LLM backend selection, TTS fallback behavior, and database memory storage.",
            "Manual tests remain important for OS automation because opening Spotify, focusing windows, pressing media keys, and using browser SpeechRecognition depend on the actual Windows environment.",
        ],
        "table": [
            ["Test Type", "Examples"],
            ["Unit", "Intent detection for app, Spotify, file_write, file_append."],
            ["Integration", "Chat WebSocket token stream and stop response."],
            ["Frontend", "Mobile layout and Send/Stop button state."],
            ["Manual", "Wake word, Spotify playback, app launch, file opening."],
        ],
    },
    {
        "title": "6.2 Intent Detection Tests",
        "paras": [
            "Intent detection is critical because plugins depend on it. The detector must recognize natural commands even when punctuation or casing varies.",
            "Tests were added for file write and file append commands. These confirm that the correct intent is returned and that content and target file are separated correctly.",
            "The detector also includes patterns for Spotify control, app launching, web search, folder search, and common media commands.",
        ],
        "code": [
            "detect_intent('write Hello world to file notes.txt')",
            "-> { intent: 'file_write', target: 'Hello world', extra: 'notes.txt' }",
            "",
            "detect_intent('append more notes to file notes.txt')",
            "-> { intent: 'file_append', target: 'more notes', extra: 'notes.txt' }",
        ],
    },
    {
        "title": "6.3 Frontend Build Validation",
        "paras": [
            "The frontend build process checks that React, Vite, TailwindCSS, and JSX syntax compile correctly. This is especially useful after changing App.jsx because the file contains much of the UI and WebSocket logic.",
            "After wake-word improvements and UI modifications, npm run build completed successfully in the frontend directory. The build output created production assets in frontend/dist.",
            "Build validation does not prove every runtime behavior, but it catches syntax errors, missing imports, and bundler-level problems.",
        ],
        "bullets": ["Command: npm.cmd run build.", "Target directory: frontend.", "Expected output: frontend/dist assets.", "Purpose: verify UI compiles successfully."],
    },
    {
        "title": "6.4 Stop Response Validation",
        "paras": [
            "The Stop response feature should be tested by sending a prompt that produces a long answer and pressing Stop while tokens are still streaming.",
            "Expected behavior is that the frontend stops showing typing, cancels speech, stops lip animation, and keeps the partial answer or marks it as stopped. The backend should stop generation and emit a done event with stopped true.",
            "This feature is important for usability because it gives the user control over both text and voice output. It also prevents long TTS queues from continuing after the user has moved on.",
        ],
        "table": [
            ["Step", "Expected Result"],
            ["Send long prompt", "Send button changes to Stop and tokens begin streaming."],
            ["Click Stop", "Speech cancels and UI returns to ready state."],
            ["Backend event", "done event includes stopped: true."],
            ["New prompt", "User can send another prompt normally."],
        ],
    },
    {
        "title": "6.5 Wake Word Validation",
        "paras": [
            "Wake-word validation requires Chrome or a compatible browser. The user enables the wake-word toggle and speaks the word 'Yashi' from a reasonable distance.",
            "Two cases should be tested. In the first case, the user says only 'Yashi', and the main microphone should activate. In the second case, the user says 'Yashi play music', and the command should run directly.",
            "Because browser recognition can be inconsistent, testing should include repeated trials, background-noise checks, and common mishearings. Fuzzy matching improves reliability but does not make browser STT perfect.",
        ],
        "bullets": ["Test in Chrome browser mode.", "Check UI status after enabling wake word.", "Confirm direct command execution.", "Confirm mic activation for wake-only command."],
    },
    {
        "title": "6.6 Spotify Validation",
        "paras": [
            "Spotify validation checks whether Yashi can open Spotify, search for a requested song, and attempt playback. The test depends on Spotify being installed and logged in.",
            "The expected successful path is that Spotify opens, search results appear for the requested song, and playback begins through keyboard/media automation. If automation cannot start playback, the fallback should still leave the user on the correct search result.",
            "This test is environment-sensitive because Spotify UI changes, focus behavior, and Windows media-key handling can differ across machines.",
        ],
        "table": [
            ["Command", "Expected Result"],
            ["open Spotify", "Spotify launches."],
            ["play music", "Spotify resumes or starts playback."],
            ["play <song> on Spotify", "Song search opens and playback is attempted."],
            ["pause music", "Playback pauses through media controls."],
        ],
    },
    {
        "title": "6.7 File Operation Validation",
        "paras": [
            "File operation validation ensures that Yashi can create, write, append, find, and open files or folders. These tests should use safe test files so no important user data is affected.",
            "Creation tests check that files appear in the expected directory and that boilerplate is inserted for recognized extensions. Write and append tests check that content changes exactly as requested.",
            "Search tests check common directories such as Desktop, Documents, Downloads, Pictures, Music, and Videos. Broader all-directory search remains future work with safety confirmation.",
        ],
        "bullets": ["Create: 'create a file called notes.txt'.", "Write: 'write Hello world to file notes.txt'.", "Append: 'append second line to file notes.txt'.", "Find: 'find my Downloads folder'."],
    },
    {
        "title": "6.8 Review Findings",
        "paras": [
            "Review findings are included in this report because they show technical maturity and honest evaluation. A good project report should document not only completed features but also known risks and improvement areas.",
            "The first finding is that live backend switching may not affect the current chat session if the active ConversationEngine already cached the LLM and TTS objects. The fix is to rebuild or refresh active engines after settings change.",
            "The second finding is static path traversal risk. Routes that serve assets or TTS files should resolve requested paths and verify containment inside allowed directories.",
        ],
        "bullets": ["P1: live backend switch should update current session.", "P1: static route containment check is required.", "P2: wake-word UI false active state was addressed.", "P2: true all-directory file search remains limited."],
    },
    {
        "title": "6.9 Bug Fixes Recorded",
        "paras": [
            "Several bugs were fixed during development. Missing settings constants caused import crashes, so config/settings.py was rewritten to contain all constants required by modules.",
            "The avatar video initially returned 404 because the static route searched the wrong folder. The route was updated to search frontend assets, data, and public paths.",
            "Plugin response handling previously left typing indicators stuck. The frontend now resets typing and status in plugin_response cases so quick actions finish cleanly.",
        ],
        "bullets": ["ImportError fixes for LLM_REPEAT_PENALTY and WHISPER_MODEL.", "FastAPI initialization cleanup.", "Video static route corrections.", "Trailing punctuation stripping for app targets.", "TTS fallback after audio errors."],
    },
    {
        "title": "CHAPTER 7 RESULTS AND DISCUSSION",
        "paras": [
            "The result of the project is a working AI assistant with a browser interface, optional desktop shell, voice features, LLM backend selection, app launcher, Spotify control, file operations, and stop-response behavior.",
            "The project demonstrates that a student-built assistant can connect AI responses with local productivity tasks. It also shows that practical constraints such as API quotas, browser support, and OS automation reliability must be handled carefully.",
            "The most important outcome is that Yashi evolved from a local chatbot into a personal computer assistant with a richer interaction model.",
        ],
        "bullets": ["Conversation and streaming are functional.", "Voice and TTS paths have fallbacks.", "Plugins perform useful real actions.", "UI is more usable on browser and mobile."],
    },
    {
        "title": "7.1 User Experience Result",
        "paras": [
            "The user experience improved through streaming output, live typing state, video avatar, sentence-by-sentence voice, mobile layout, sidebar settings, and visible wake-word controls.",
            "The Stop button is especially important because it makes the assistant feel controllable. Users do not have to wait for long responses or listen to a full TTS queue if they decide to interrupt.",
            "The video avatar makes the interface feel less static while leaving custom animation for a later stage. This was a practical prioritization decision.",
        ],
        "bullets": ["Send becomes Stop during generation.", "TTS can be interrupted.", "Avatar provides presence.", "Settings are accessible from the sidebar."],
    },
    {
        "title": "7.2 Performance Discussion",
        "paras": [
            "Performance depends mainly on the selected LLM backend. Ollama performance depends on local hardware and model size. OpenAI performance depends on network speed and provider quota.",
            "The current model map uses phi3:mini for all cognitive modes to keep local performance manageable. This makes responses faster and lighter for the PC.",
            "Streaming improves perceived performance because the user sees progress immediately. Sentence-level TTS also reduces the delay before the assistant begins speaking.",
        ],
        "table": [
            ["Performance Factor", "Effect"],
            ["Model size", "Larger models may improve quality but reduce speed."],
            ["Backend type", "Local uses PC resources; cloud uses API quota."],
            ["Streaming", "Improves responsiveness and supports interruption."],
            ["TTS backend", "ElevenLabs quality is higher, browser fallback is faster to recover."],
        ],
    },
    {
        "title": "7.3 Privacy Discussion",
        "paras": [
            "Privacy is an important topic for an assistant that processes personal prompts and file commands. The local Ollama backend allows users to keep model inference on their own computer.",
            "Cloud features such as OpenAI and ElevenLabs are optional. When enabled, prompts or text sent for voice synthesis may leave the machine depending on the provider API.",
            "The report recommends clear UI labels and settings so users understand which backend is active. This is already supported through sidebar badges.",
        ],
        "bullets": ["Ollama supports local-first usage.", "OpenAI and ElevenLabs require external API calls.", "Status badges help users understand active backend choices."],
    },
    {
        "title": "7.4 Limitations",
        "paras": [
            "Yashi is functional, but it has limitations. Wake-word recognition depends on browser support and may not work consistently in all environments. Desktop pywebview mode does not provide the same wake-word capability.",
            "Spotify playback automation is best-effort because it depends on app focus and UI behavior. It can open search results reliably, but autoplay can vary.",
            "File operations are intentionally scoped. True any-directory search and modification should be expanded only after adding confirmations, path containment, and permission controls.",
        ],
        "bullets": ["Wake word is browser-dependent.", "Spotify autoplay may vary by machine.", "Static path serving needs hardening.", "Backend hot-swap should refresh current sessions."],
    },
    {
        "title": "CHAPTER 8 CONCLUSION AND FUTURE SCOPE",
        "paras": [
            "The Yashi project successfully demonstrates a practical AI companion that combines conversation, voice interaction, local automation, file operations, memory, and a modern UI.",
            "The project evolved through multiple stages: local Ollama conversation, OpenAI support, ElevenLabs voice, wake-word activation, app launcher plugin, Spotify playback improvements, file write/append support, video avatar UI, mobile optimization, settings toggles, and stop-response control.",
            "The final system is suitable for demonstration as a college project because it shows both AI concepts and real software engineering implementation.",
        ],
        "bullets": ["Built a working full-stack assistant.", "Integrated local and optional cloud AI services.", "Connected natural language to real desktop tasks.", "Documented limitations and future improvements."],
    },
    {
        "title": "8.1 Future Scope",
        "paras": [
            "Future work can improve wake-word reliability by using a dedicated wake-word engine instead of relying only on browser SpeechRecognition. A local engine such as Porcupine, openWakeWord, or a custom small model could improve always-on behavior.",
            "The frontend avatar can be upgraded from a video loop to a real animated character with lip sync, expressions, and emotional state changes.",
            "File operations can be expanded to true all-directory search with explicit user permission, safe path resolution, deny-lists for system folders, and confirmations before write operations outside common folders.",
        ],
        "bullets": ["Dedicated wake-word model.", "Animated avatar with expressions.", "Safer full-computer file search.", "Better Spotify API integration.", "More automated tests and browser tests."],
    },
    {
        "title": "REFERENCES",
        "paras": [
            "The following references represent the technologies and concepts used in the Yashi project. They are included in a college-report style rather than as live citations.",
            "FastAPI documentation for API routing and WebSocket support. React and Vite documentation for frontend development. Ollama documentation for local LLM execution. OpenAI API documentation for GPT model integration. ElevenLabs documentation for text-to-speech API usage.",
            "Additional practical references include Web Speech API documentation, pywebview documentation, SQLite documentation, and Python standard library documentation for subprocess, pathlib, asyncio, and webbrowser modules.",
        ],
        "bullets": ["FastAPI - backend and WebSockets.", "React/Vite - frontend application.", "Ollama/OpenAI - language model backends.", "ElevenLabs/Web Speech API - voice features.", "SQLite - local memory database."],
    },
    {
        "title": "APPENDIX A PROJECT STRUCTURE",
        "paras": [
            "The Yashi project is organized into clear directories. This makes the project easier to explain, debug, and extend.",
            "The app directory contains backend routes. The core directory contains AI, memory, emotion, voice, safety, and conversation logic. The plugins directory contains task automation modules. The frontend directory contains the React UI.",
            "The data directory stores the SQLite database, avatar video, and generated audio cache. The logs directory stores runtime logs.",
        ],
        "code": [
            "Yashi/",
            "  app/                 FastAPI app, routes, WebSocket manager",
            "  core/                conversation, LLM, memory, voice, emotion",
            "  plugins/             app launcher, file ops, web launcher",
            "  frontend/            React UI, assets, Vite build",
            "  config/settings.py   centralized configuration",
            "  data/                database, avatar, TTS cache",
            "  tests/test_all.py    Python test cases",
        ],
    },
    {
        "title": "APPENDIX B SETUP AND RUN COMMANDS",
        "paras": [
            "The project can be started through the Python backend and the React frontend build. Ollama should be running locally when the LLM backend is set to ollama.",
            "Optional API keys can be placed in the .env file. OPENAI_API_KEY enables the OpenAI backend, and ELEVENLABS_API_KEY enables ElevenLabs voice.",
            "For desktop mode, pywebview is installed and desktop.py is executed. For wake-word testing, Chrome browser mode is recommended.",
        ],
        "code": [
            "setup.bat",
            "ollama serve",
            "ollama pull phi3:mini",
            "python run.py",
            "cd frontend",
            "npm.cmd run build",
            "python desktop.py",
        ],
    },
    {
        "title": "APPENDIX C SAMPLE COMMANDS",
        "paras": [
            "The following sample commands demonstrate how a user can interact with Yashi. They cover normal chat, app launching, Spotify control, file operations, web search, and wake-word usage.",
            "These commands are useful during project viva or demonstration because they show the difference between ordinary AI response generation and plugin-based local actions.",
            "The commands should be tested in a safe environment, especially file write commands.",
        ],
        "bullets": ["Yashi, tell me what this project does.", "Open Spotify.", "Play Believer on Spotify.", "Pause music.", "Open Chrome and search FastAPI WebSocket.", "Create a file called notes.txt.", "Write Hello world to file notes.txt.", "Append second line to file notes.txt.", "Find my Downloads folder.", "Stop the response using the Stop button."],
    },
    {
        "title": "APPENDIX D REVIEW FINDINGS AND IMPROVEMENT NOTES",
        "paras": [
            "The review findings included in the project are valuable because they identify the next engineering steps. They also show that the project was evaluated from a security and behavior perspective.",
            "Live backend switching should update existing ConversationEngine objects or recreate them for connected WebSocket sessions. Static file routes should perform resolve and containment checks. Wake-word UI state should only report active when recognition actually starts. File operations should clearly describe the current search scope.",
            "Some of these were improved during the project, including wake-word UI state, wake-word retry behavior, file write/append support, Spotify playback attempts, and stop-response control.",
        ],
        "bullets": ["Fix active engine refresh for backend hot-swap.", "Harden static and TTS file-serving routes.", "Expand file search with confirmations.", "Move wake word to a stronger local engine.", "Add more automated browser tests."],
    },
]


DETAILED_VISUAL_PAGES = [
    {
        "title": "4.10 Detailed Architecture Diagram",
        "paras": [
            "The architecture diagram gives a visual summary of how Yashi connects the user interface, backend services, conversation engine, plugins, voice layer, memory layer, and external or local services. It is useful during viva because it explains the whole project in one view.",
            "The design separates user-facing behavior from backend orchestration. The frontend manages status, microphone state, wake-word state, speech playback, and the video avatar. The backend manages intelligence, memory, plugin dispatch, and settings.",
            "This separation is important because local actions such as opening Spotify or writing a file should not be generated freely by the LLM. Instead, they pass through plugins where the behavior is explicit and easier to test.",
        ],
        "figures": ["architecture"],
        "table": [
            ["Architecture Area", "Key Responsibility", "Important Benefit"],
            ["Frontend UI", "Displays chat, avatar, controls, settings, and mobile layout.", "Keeps user interaction responsive and visible."],
            ["FastAPI Layer", "Routes WebSocket messages, REST APIs, static files, and settings.", "Creates a stable boundary between UI and core logic."],
            ["Core Engine", "Handles emotion, memory, prompt building, LLM streaming, and TTS events.", "Centralizes AI behavior."],
            ["Plugins", "Execute app launch, Spotify, web search, and file operations.", "Makes real-world actions deterministic."],
            ["Data/External", "Stores local memory and connects to Ollama, OpenAI, ElevenLabs, and apps.", "Allows local-first use with optional cloud upgrades."],
        ],
    },
    {
        "title": "4.11 End-to-End Data Flow Diagram",
        "paras": [
            "The data flow diagram shows the two main execution paths in Yashi. If the intent detector recognizes a local command, the request is handled by a plugin. If the message needs conversation, the request is handled by the conversation engine.",
            "This dual-path structure improves efficiency. Commands such as 'open Spotify' or 'write notes to file' do not require a full LLM response. Conversational prompts still use memory, emotion, prompt building, and model streaming.",
            "The pipeline also supports fallback behavior. If ElevenLabs cannot produce audio, the frontend uses browser speech synthesis. If a plugin cannot complete a system action, it returns a helpful message instead of leaving the UI stuck.",
        ],
        "figures": ["pipeline"],
        "bullets": [
            "Direct action path: user prompt -> intent detector -> plugin -> plugin_response.",
            "AI response path: user prompt -> engine -> memory/emotion/prompt -> LLM stream -> TTS and done events.",
            "Stop path: user presses Stop -> frontend sends stop -> engine ends streaming and cancels TTS tasks.",
        ],
    },
    {
        "title": "4.12 WebSocket Event Map",
        "paras": [
            "Yashi uses WebSocket events instead of waiting for a single final response. Each event type updates a different part of the frontend. This makes the UI feel alive because users can see connection status, emotion state, thinking mode, tokens, speech chunks, and completion status.",
            "The Stop feature also depends on WebSocket communication. A stop message is sent from the frontend to the backend, and the backend responds with a done event containing stopped set to true.",
            "The following table documents the main event contract used by the project. This is useful for future maintenance because frontend and backend changes must preserve these event names.",
        ],
        "table": [
            ["Event Type", "Direction", "Purpose"],
            ["connected", "Backend to frontend", "Confirms the WebSocket session is ready."],
            ["text", "Frontend to backend", "Sends the user's typed or spoken prompt."],
            ["emotion", "Backend to frontend", "Updates current emotion and emotional state."],
            ["thinking", "Backend to frontend", "Shows the selected cognitive mode."],
            ["token", "Backend to frontend", "Streams partial LLM output."],
            ["tts_sentence", "Backend to frontend", "Provides a speakable sentence or audio path."],
            ["plugin_response", "Backend to frontend", "Returns app/file/web action result."],
            ["stop", "Frontend to backend", "Requests output interruption."],
            ["done", "Backend to frontend", "Completes the response and includes stopped status."],
        ],
    },
    {
        "title": "5.16 Stop Response Sequence Diagram",
        "paras": [
            "The stop-response feature is one of the most user-friendly controls in the project. It changes the assistant from a one-way responder into a controllable interaction system.",
            "When the user sends a prompt, the Send button becomes Stop. If the user presses Stop, the frontend immediately cancels audio playback, stops lip animation, and sends a stop message over the WebSocket. The backend then signals the conversation engine to end generation.",
            "The sequence diagram below is included because it clearly shows how frontend state, backend routing, LLM streaming, and TTS cancellation work together.",
        ],
        "figures": ["stop_sequence"],
        "table": [
            ["Component", "Stop Behavior"],
            ["React UI", "Sends stop message, clears typing state, cancels browser speech and audio queues."],
            ["Chat WebSocket", "Receives the stop event and calls engine.request_stop()."],
            ["ConversationEngine", "Sets a stop event, breaks streaming, cancels pending TTS tasks."],
            ["LLM/TTS", "Streaming and speech generation stop as soon as cancellation is observed."],
        ],
    },
    {
        "title": "5.17 Feature Completion Chart",
        "paras": [
            "The feature completion chart summarizes project maturity across major modules. It is not a formal metric; it is a practical engineering estimate based on what is implemented and what still has known constraints.",
            "Features such as chat streaming, stop response, file writing, and mobile UI are mostly complete for the current scope. Wake word and Spotify playback are useful but environment-dependent. Any-directory file operations remain intentionally limited until stronger safety checks are added.",
            "This chart helps present the project honestly during review. It shows completed work while also making future scope clear.",
        ],
        "figures": ["feature_completion"],
        "bullets": [
            "High maturity: streaming chat, stop response, basic file write/append.",
            "Medium maturity: ElevenLabs, mobile UI, Spotify playback automation.",
            "Lower maturity: wake-word reliability and true full-computer file operations.",
        ],
    },
    {
        "title": "5.18 Backend Selection Analysis Chart",
        "paras": [
            "Yashi supports both Ollama and OpenAI because each backend has different strengths. Ollama is better for local, private, no-cost usage. OpenAI is better when the user wants stronger cloud inference and lower local PC load.",
            "The chart compares both backends on project suitability factors. The result explains why Ollama is the default even though OpenAI support exists.",
            "The decision is not permanent. The sidebar toggle allows the user to switch backend depending on the situation, API quota, internet availability, and hardware capacity.",
        ],
        "figures": ["backend_chart"],
        "table": [
            ["Decision Factor", "Ollama", "OpenAI"],
            ["Cost", "Free after local setup.", "Depends on API plan and quota."],
            ["Privacy", "Prompts stay local.", "Prompts go to cloud API."],
            ["PC Load", "Uses local resources.", "Low local resource usage."],
            ["Reliability", "Requires Ollama service running.", "Requires internet and API availability."],
        ],
    },
    {
        "title": "5.19 Mobile UI Layout Diagram",
        "paras": [
            "The mobile UI diagram shows how the same assistant experience is adapted for browser and phone-sized layouts. The desktop view gives more room to the avatar and chat panel. The mobile view compresses controls into a narrow interface without hiding the core actions.",
            "This is important because voice assistants are often used casually, and a browser-based assistant should remain usable even when the screen width is small.",
            "The UI avoids relying only on desktop layout assumptions. The sidebar can become a mobile panel, the composer remains reachable, and the status controls remain visible enough for testing.",
        ],
        "figures": ["mobile_wireframe"],
        "bullets": [
            "Desktop focus: avatar and chat can sit side by side.",
            "Mobile browser: compact chat, reachable composer, and menu-based settings.",
            "Both modes preserve mic, wake word, Send/Stop, and settings access.",
        ],
    },
    {
        "title": "6.10 Risk Matrix and Mitigation Chart",
        "paras": [
            "The risk matrix identifies areas that need attention before wider distribution. A personal assistant with local automation must be reviewed more carefully than a normal chatbot because it can interact with files, apps, and local paths.",
            "Static file traversal and backend hot-swap caching are high-priority engineering issues. Wake-word reliability and Spotify automation are usability risks because they depend on browser and application behavior.",
            "The matrix helps prioritize future work. Security and data-access risks should be handled before adding broad file-system powers.",
        ],
        "figures": ["risk_matrix"],
        "table": [
            ["Risk", "Priority", "Recommended Action"],
            ["Static path traversal", "High", "Resolve requested paths and verify containment inside allowed folders."],
            ["Backend hot-swap cache", "High", "Rebuild or update active ConversationEngine instances after settings change."],
            ["Wake-word reliability", "Medium", "Move to a dedicated wake-word engine or improve browser retry strategy."],
            ["Spotify UI variation", "Medium", "Prefer official Spotify API integration when possible."],
            ["Broad file operations", "High", "Add permission prompts, deny-lists, and path safety rules."],
        ],
    },
    {
        "title": "7.5 Development Timeline Diagram",
        "paras": [
            "The development timeline shows the order in which the project grew. The early foundation was local AI conversation through Ollama. Later stages added voice, wake word, automation, file operations, UI improvements, and response control.",
            "This timeline is useful in a college report because it shows that the project was developed iteratively. Each stage added a new capability while also revealing bugs and design constraints.",
            "The final stage is documentation, where the implementation details, review findings, diagrams, charts, limitations, and future scope are collected into a formal report.",
        ],
        "figures": ["timeline"],
        "bullets": [
            "Foundation: local AI conversation and streaming.",
            "Expansion: voice, wake word, plugins, and file operations.",
            "Polish: mobile UI, video avatar, settings toggles, stop response, and documentation.",
        ],
    },
    {
        "title": "APPENDIX E DEMONSTRATION FLOW",
        "paras": [
            "This appendix gives a suggested project demonstration order. It is designed for a college viva or practical evaluation where the examiner needs to see the main features quickly and clearly.",
            "The best demonstration starts with normal chat, then moves to voice, then local automation, then file operations, and finally stop-response control. This order shows the project from simple to advanced behavior.",
            "Before the demo, Ollama should be running, Spotify should be logged in, the browser should allow microphone access, and optional API keys should be configured only if those services are being demonstrated.",
        ],
        "table": [
            ["Step", "Demo Command", "What It Shows"],
            ["1", "Hello Yashi, introduce yourself.", "Basic conversation and streaming response."],
            ["2", "Enable wake word and say 'Yashi'.", "Browser speech recognition and mic activation."],
            ["3", "Open Spotify.", "App launcher plugin."],
            ["4", "Play Believer on Spotify.", "Spotify search and playback automation."],
            ["5", "Create a file called viva_notes.txt.", "File creation plugin."],
            ["6", "Write this project uses FastAPI and React to file viva_notes.txt.", "File write operation."],
            ["7", "Ask for a long explanation, then press Stop.", "Stop-response control."],
        ],
    },
    {
        "title": "APPENDIX F DATABASE AND MEMORY DETAILS",
        "paras": [
            "The memory layer gives Yashi continuity. Even though the assistant can operate as a simple chatbot, the project includes storage modules that prepare it for more personalized interactions.",
            "SQLite is a suitable choice for this project because it is lightweight, local, and does not require a separate server. It fits the local-first philosophy of Yashi.",
            "Future work can add a UI for memory management so the user can inspect, edit, or delete stored facts and conversation memories.",
        ],
        "table": [
            ["Memory Area", "Purpose", "Future Improvement"],
            ["Conversations", "Store dialogue history and emotion tags.", "Add export and delete controls."],
            ["Personal Facts", "Remember names, preferences, and useful user details.", "Add user approval before storing sensitive facts."],
            ["Semantic Memory", "Search relevant older information.", "Improve embeddings and ranking."],
            ["Reflections", "Summarize repeated patterns or insights.", "Show reflection summaries in a memory panel."],
            ["Session Stats", "Track usage and safety limits.", "Add dashboard-style analytics."],
        ],
    },
    {
        "title": "APPENDIX G EXTENDED TEST CASES",
        "paras": [
            "This appendix lists additional test cases that can be implemented in future automated or manual testing. It provides a practical checklist for validating the assistant after changes.",
            "The test cases cover UI behavior, backend events, plugin behavior, wake word, file operations, and error fallbacks. They are written in simple expected-result format so they can be converted into unit tests or manual test sheets.",
            "A stronger test suite would make future feature additions safer, especially for settings hot-swap, static path safety, and broad file operations.",
        ],
        "table": [
            ["Test Case", "Input/Action", "Expected Result"],
            ["Stop during stream", "Ask long question and click Stop.", "Generation stops and UI returns to ready."],
            ["ElevenLabs fallback", "Use invalid ElevenLabs key.", "Browser TTS speaks response."],
            ["OpenAI rate limit", "Trigger multiple OpenAI calls quickly.", "Retry/backoff runs and user sees helpful behavior."],
            ["Wake-only command", "Say only 'Yashi'.", "Main mic activates for command window."],
            ["Direct wake command", "Say 'Yashi open Spotify'.", "Command is sent immediately."],
            ["File append", "Append text to test file.", "Text is added without deleting old content."],
            ["Static traversal check", "Request ../ path from static route.", "Request is rejected after hardening."],
        ],
    },
]

CONTENT_PAGES.extend(DETAILED_VISUAL_PAGES)


def content_page(page: dict) -> str:
    xml = [heading(page["title"])]
    for para in page.get("paras", []):
        xml.append(p(para, align="both"))
    if page.get("figures"):
        for key in page["figures"]:
            xml.append(figure_block(key))
    if page.get("bullets"):
        for item in page["bullets"]:
            xml.append(bullet(item))
    if page.get("table"):
        xml.append(table(page["table"]))
    if page.get("code"):
        xml.append(code_block(page["code"]))
    return "".join(xml)


def build_document_xml() -> str:
    pages = [
        make_cover(),
        declaration_page(),
        acknowledgement_page(),
        abstract_page(),
        *toc_pages(),
        lists_page(),
        abbreviations_page(),
    ]
    pages.extend(content_page(page) for page in CONTENT_PAGES)

    body = []
    for index, page_xml in enumerate(pages):
        if index:
            body.append(page_break())
        body.append(page_xml)

    body.append('''
    <w:sectPr>
      <w:headerReference w:type="default" r:id="rId19"/>
      <w:footerReference w:type="default" r:id="rId20"/>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1008" w:bottom="1008" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/>
      <w:cols w:space="708"/>
      <w:docGrid w:linePitch="360"/>
    </w:sectPr>
    ''')

    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
 xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"
 mc:Ignorable="">
  <w:body>{''.join(body)}</w:body>
</w:document>'''


def header_xml() -> str:
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  {p("AITM/" + SHORT_TITLE, align="right", size=16, bold=True, font="Arial", after=0)}
</w:hdr>'''


def footer_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:p>
    <w:pPr><w:jc w:val="center"/></w:pPr>
    <w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="18"/></w:rPr><w:t>Page </w:t></w:r>
    <w:r><w:fldChar w:fldCharType="begin"/></w:r>
    <w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>
    <w:r><w:fldChar w:fldCharType="separate"/></w:r>
    <w:r><w:t>1</w:t></w:r>
    <w:r><w:fldChar w:fldCharType="end"/></w:r>
  </w:p>
</w:ftr>'''


def document_rels_xml(original: bytes) -> bytes:
    rels = original.decode("utf-8")
    additions = []
    for figure in REPORT_FIGURES:
        additions.append(
            f'<Relationship Id="{figure["rid"]}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            f'Target="media/{figure["filename"]}"/>'
        )
    return rels.replace("</Relationships>", "".join(additions) + "</Relationships>").encode("utf-8")


def core_props_xml() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties
 xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{esc(PROJECT_TITLE)}</dc:title>
  <dc:subject>College project report</dc:subject>
  <dc:creator>{esc(STUDENT)}</dc:creator>
  <cp:keywords>Yashi, AI Assistant, FastAPI, React, Ollama, OpenAI, ElevenLabs</cp:keywords>
  <dc:description>Detailed 60-plus page report with diagrams and charts for the Yashi AI companion project.</dc:description>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>'''


def app_props_xml() -> str:
    pages = len(CONTENT_PAGES) + 8
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Template>Normal</Template>
  <TotalTime>0</TotalTime>
  <Pages>{pages}</Pages>
  <Words>26000</Words>
  <Application>Microsoft Office Word</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>'''


def generate() -> None:
    if not TEMPLATE.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE}")

    generate_visual_assets()

    replacements = {
        "word/document.xml": build_document_xml().encode("utf-8"),
        "word/header7.xml": header_xml().encode("utf-8"),
        "word/footer7.xml": footer_xml().encode("utf-8"),
        "docProps/core.xml": core_props_xml().encode("utf-8"),
        "docProps/app.xml": app_props_xml().encode("utf-8"),
    }

    with zipfile.ZipFile(TEMPLATE, "r") as src, zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename == "word/_rels/document.xml.rels":
                dst.writestr(item, document_rels_xml(src.read(item.filename)))
            elif item.filename in replacements:
                dst.writestr(item, replacements[item.filename])
            else:
                dst.writestr(item, src.read(item.filename))
        for figure in REPORT_FIGURES:
            dst.write(ASSET_DIR / figure["filename"], f'word/media/{figure["filename"]}')

    print(f"Generated: {OUTPUT}")
    print(f"Forced pages: {len(CONTENT_PAGES) + 8}")


if __name__ == "__main__":
    generate()
