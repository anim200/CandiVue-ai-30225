"""Builds the project's diagrams (docs/diagrams/*.pdf) from this one file.

Each figure is drawn as an SVG inside a small HTML page, then printed to a
PDF with Microsoft Edge (headless). Edit the figure functions below and run:

    python docs/diagrams/src/build_diagrams.py            (all figures)
    python docs/diagrams/src/build_diagrams.py fig4 fig7  (some figures)

Node names in the LangGraph figures are the real ones in
backend/app/graphs/, so a diagram can be checked against the code.
The HTML pages go to docs/diagrams/src/build/ (ignored by git).
"""

import html
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent  # docs/diagrams
BUILD = HERE / "build"
EDGE = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]
FONT = "'Times New Roman', Times, serif"
EMOJI = "'Segoe UI Emoji', 'Apple Color Emoji', sans-serif"

# Node colours of the LangGraph figures (fill, border): the same as before.
NODE = {
    "blue": ("#DAE8FC", "#6C8EBF"),  # load / collect / save
    "green": ("#D5E8D4", "#82B366"),  # work steps
    "orange": ("#FFE6CC", "#D79B00"),  # side paths (skip, OCR, exclusion)
    "yellow": ("#FFF2CC", "#D6B656"),  # decisions
    "purple": ("#E1D5E7", "#9673A6"),  # human review (interrupt)
    "white": ("#FFFFFF", "#999999"),
}
LINE = "#555555"


class Svg:
    """A drawing: shapes are added in order and written as one SVG."""

    def __init__(self, width: int, height: int):
        """An empty drawing of the given size (pixels)."""
        self.width, self.height, self.parts = width, height, []

    # ---------- text ----------
    def text(self, x, y, value, size=15, weight="normal", anchor="middle",
             color="#222", italic=False, font=FONT):
        """One line of text; (x, y) is its baseline point."""
        style = "font-style:italic;" if italic else ""
        self.parts.append(
            f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}" text-anchor="{anchor}" '
            f'style="{style}">{html.escape(value)}</text>'
        )

    def lines(self, cx, cy, rows, color="#222"):
        """Several centred lines around (cx, cy). rows: (text, size, weight)."""
        gap = 4
        total = sum(size for _t, size, _w in rows) + gap * (len(rows) - 1)
        y = cy - total / 2
        for value, size, weight in rows:
            y += size
            self.text(cx, y - size * 0.18, value, size, weight, color=color)
            y += gap

    # ---------- shapes of the LangGraph figures ----------
    def node(self, x, y, w, h, colour, title, *notes, bold=False, ai=0):
        """A rounded node: its name, then smaller notes. ai: AI requests."""
        fill, stroke = NODE[colour]
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>'
        )
        rows = [(title, 16, "bold" if bold or notes else "normal")]
        rows += [(note, 13, "normal") for note in notes]
        self.lines(x + w / 2, y + h / 2, rows)
        if ai:
            self.badge(x + w - 6, y - 9, f"AI x{ai}" if ai > 1 else "AI x1")

    def badge(self, right, y, label):
        """A small pill above a node's corner, e.g. "AI x1"."""
        w = 9 * len(label) + 10
        self.parts.append(
            f'<rect x="{right - w}" y="{y}" width="{w}" height="18" rx="9" '
            f'fill="#FFF7E6" stroke="#E0A030" stroke-width="1"/>'
        )
        self.text(right - w / 2, y + 13.5, label, 11.5, "bold", color="#9A5B00")

    def terminal(self, cx, cy, label):
        """START or END: an ellipse."""
        fill, stroke = NODE["blue"]
        self.parts.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="75" ry="23" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.3"/>'
        )
        self.text(cx, cy + 6, label, 17, "bold")

    def diamond(self, cx, cy, w, h, title):
        """A decision."""
        fill, stroke = NODE["yellow"]
        points = f"{cx},{cy - h / 2} {cx + w / 2},{cy} {cx},{cy + h / 2} {cx - w / 2},{cy}"
        self.parts.append(
            f'<polygon points="{points}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"/>'
        )
        self.text(cx, cy + 6, title, 16, "bold")

    def group(self, x, y, w, h, title, fill="#F6F6F6"):
        """A dashed frame around related nodes, with its title top left."""
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" '
            f'stroke="#9A9A9A" stroke-width="1.2" stroke-dasharray="7 5"/>'
        )
        self.text(x + 16, y + 24, title, 14.5, "bold", anchor="start", color="#555")

    def note(self, x, y, w, h, *rows, colour="white"):
        """A small dotted note box (plain text, left aligned)."""
        fill, stroke = NODE[colour]
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1" stroke-dasharray="2 3"/>'
        )
        for i, row in enumerate(rows):
            weight = "bold" if i == 0 else "normal"
            self.text(x + 10, y + 19 + i * 17, row, 13, weight, anchor="start", color="#333")

    def arrow(self, points, dashed=False, label=None, at=None, head=True, colour=LINE):
        """A line through the points, with an arrowhead at the end and an
        optional label on a white background at `at` (default: midway)."""
        path = " ".join(f"{x},{y}" for x, y in points)
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        end = ' marker-end="url(#head)"' if head else ""
        self.parts.append(
            f'<polyline points="{path}" fill="none" stroke="{colour}" '
            f'stroke-width="1.4"{dash}{end}/>'
        )
        if label:
            if at is None:
                (x1, y1), (x2, y2) = points[len(points) // 2 - 1], points[len(points) // 2]
                at = ((x1 + x2) / 2, (y1 + y2) / 2)
            self.label(at[0], at[1], label)

    def label(self, cx, cy, value, size=13.5):
        """A label on a white background (for lines)."""
        w = len(value) * size * 0.47 + 10
        self.parts.append(
            f'<rect x="{cx - w / 2}" y="{cy - size * 0.75}" width="{w}" '
            f'height="{size * 1.45}" fill="#FFFFFF"/>'
        )
        self.text(cx, cy + size * 0.33, value, size, color="#333")

    def caption(self, value):
        """The figure caption at the bottom."""
        self.text(self.width / 2, self.height - 22, value, 17, "bold")

    def raw(self, svg: str):
        """Any other SVG."""
        self.parts.append(svg)

    def write(self) -> str:
        """The finished SVG."""
        defs = (
            '<defs><marker id="head" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{LINE}"/></marker></defs>'
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" '
            f'height="{self.height}" viewBox="0 0 {self.width} {self.height}">'
            f'<rect width="100%" height="100%" fill="#FFFFFF"/>{defs}'
            + "".join(self.parts)
            + "</svg>"
        )


# ======================================================================
# Figure 1: High level system diagram (for any reader, no technical terms)
# ======================================================================
WHO = {  # who does a step: (card colour, label)
    "interviewer": ("#1A8F7F", "INTERVIEWER"),
    "system": ("#F2A630", "SYSTEM (AUTOMATIC)"),
    "candidate": ("#2F6DB5", "CANDIDATE"),
    "both": ("#6A55B8", "INTERVIEWER + CANDIDATE"),
}


def card(s, x, y, number, who, icon, *rows, w=214, h=126):
    """A step card: number badge, icon, who does it, and what happens."""
    colour, label = WHO[who]
    s.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{colour}"/>')
    s.raw(f'<circle cx="{x + 4}" cy="{y + 2}" r="16" fill="#FFFFFF" stroke="{colour}" stroke-width="2.4"/>')
    s.text(x + 4, y + 7.5, str(number), 14, "bold", color="#222")
    s.text(x + w / 2, y + 30, icon, 22, font=EMOJI)
    s.text(x + w / 2, y + 49, label, 11.5, "bold", color="#FFFFFF")
    for i, row in enumerate(rows):
        s.text(x + w / 2, y + 69 + i * 18, row, 15, color="#FFFFFF")


def pill(s, cx, cy, label):
    """The Start / End pill."""
    s.raw(f'<rect x="{cx - 46}" y="{cy - 25}" width="92" height="50" rx="25" fill="#3A3A3A"/>')
    s.text(cx, cy + 6, label, 18, "bold", color="#FFFFFF")


def fig1() -> Svg:
    """The whole process in four stages: who does what."""
    s = Svg(1440, 1040)
    xs = [320, 566, 812, 1058]
    w, h = 214, 126
    lanes = [
        ("1. Prepare", "the Job", "#EAF4F2", [
            (1, "interviewer", "\U0001F4DD", "Describe the role to the", "Hiring Assistant: skills,", "experience, must-haves"),
            (2, "system", "\U0001F916", "Write the job description,", "using trusted reference", "documents when useful"),
            (3, "interviewer", "\u2705", "Review and approve the", "job description"),
            (4, "system", "\U0001F4E2", "After the interviewer says", "Post: publish the job on the", "job board with a form link"),
        ]),
        ("2. Find the", "Best CVs", "#FEF5E4", [
            (5, "candidate", "\U0001F4E8", "Apply through the online", "form: CV and an optional", "face photo"),
            (6, "system", "\U0001F4C4", "Collect the CVs and read", "them, including scanned", "ones"),
            (7, "system", "\U0001F4CA", "Score each candidate from", "0 to 100 and rank them,", "with reasons"),
            (8, "system", "\U0001F501", "Suggest past applicants", "who fit and agreed to be", "considered"),
        ]),
        ("3. Hold the", "Interview", "#ECF0F7", [
            (9, "interviewer", "\U0001F4C5", "Shortlist, pick free times", "and confirm the", "invitations"),
            (10, "candidate", "\U0001F4E7", "Get the link by email,", "enter the emailed code,", "check in with a photo"),
            (11, "both", "\U0001F3A5", "Video interview; the", "assistant suggests", "questions to the interviewer"),
            (12, "system", "\U0001F4AC", "Write live notes: who", "said what, and when"),
        ]),
        ("4. Assess", "and Decide", "#F1EEF7", [
            (13, "system", "\U0001F50D", "Check each answer against", "the job and trusted", "documents"),
            (14, "system", "\U0001F4CB", "Combine CV and interview", "results into one report", "with evidence"),
            (15, "interviewer", "\u2705", "Review and approve each", "report"),
            (16, "interviewer", "\U0001F91D", "Compare the ranked", "candidates, decide, send", "the selection email"),
        ]),
    ]
    joins = ["Job posted with the form link", "Ranked list ready", "When the interview ends"]
    top, lane_h, gap = 20, 196, 22
    for i, (name1, name2, fill, steps) in enumerate(lanes):
        y0 = top + i * (lane_h + gap)
        s.raw(f'<rect x="20" y="{y0}" width="1400" height="{lane_h}" rx="10" fill="{fill}"/>')
        s.text(40, y0 + lane_h / 2 - 4, name1, 20, "bold", anchor="start")
        s.text(40, y0 + lane_h / 2 + 20, name2, 20, "bold", anchor="start")
        cy = y0 + 36
        for j, (number, who, icon, *rows) in enumerate(steps):
            card(s, xs[j], cy, number, who, icon, *rows)
            if j:
                s.arrow([(xs[j - 1] + w, cy + h / 2), (xs[j], cy + h / 2)])
        if i == 0:
            pill(s, 230, cy + h / 2, "Start")
            s.arrow([(276, cy + h / 2), (xs[0], cy + h / 2)])
        if i == len(lanes) - 1:
            pill(s, 1350, cy + h / 2, "End")
            s.arrow([(xs[3] + w, cy + h / 2), (1304, cy + h / 2)])
        else:
            mid = y0 + lane_h + gap / 2
            next_top = y0 + lane_h + gap + 36
            s.arrow([(xs[3] + w / 2, cy + h), (xs[3] + w / 2, mid), (xs[0] + w / 2, mid),
                     (xs[0] + w / 2, next_top)], label=joins[i], at=((xs[0] + xs[3] + w) / 2, mid))

    y = top + 4 * (lane_h + gap) + 14
    s.text(40, y + 4, "Who does each step:", 16, "bold", anchor="start")
    x = 230
    for who in ("interviewer", "system", "candidate", "both"):
        colour, label = WHO[who]
        nice = {"interviewer": "Interviewer", "system": "System (automatic)",
                "candidate": "Candidate", "both": "Interviewer and candidate"}[who]
        s.raw(f'<rect x="{x}" y="{y - 13}" width="22" height="18" rx="3" fill="{colour}"/>')
        s.text(x + 30, y + 2, nice, 15, anchor="start")
        x += 52 + len(nice) * 8
    s.text(40, y + 34, "Candidates never see scores, rankings or reports; only interviewers can. Nothing is posted or sent,",
           15, anchor="start", color="#444")
    s.text(40, y + 54, "and no report is final, before the interviewer approves it.", 15, anchor="start", color="#444")
    s.caption("Figure 1: High Level System Diagram")
    return s


# ======================================================================
# Figure 2: Detailed architecture (every step with its parts and data)
# ======================================================================
KIND = {  # kind of step: card colour, legend name
    "web": ("#2F6DB5", "Web App + API (FastAPI, React)"),
    "assistant": ("#1A8F7F", "Hiring Assistant chatbot (LangGraph 1)"),
    "review": ("#C2185B", "Human review (LangGraph interrupt)"),
    "workflow": ("#F2A630", "Background LangGraph workflows (2-5)"),
    "service": ("#6A55B8", "Backend services (collector, identity, media, transcriber)"),
}
SERVICE = {"ai": ("#FFF4E0", "#E0A030", "\u2728"), "ext": ("#EAF2FB", "#5B8BC9", "")}
STORE = {"db": ("\U0001F5C4\uFE0F", "Database"), "vec": ("\U0001F9E0", "Vector store"),
         "cv": ("\U0001F4C1", "CV folder")}
CARD_W, CARD_H, SLOT = 228, 118, 256


def step_card(s, x, y, number, kind, icon, role, title, *rows):
    """A step of Figure 2: number, icon, role, title and two short lines."""
    colour = KIND[kind][0]
    s.raw(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="9" fill="{colour}"/>')
    s.raw(f'<circle cx="{x + 4}" cy="{y + 2}" r="15" fill="#FFFFFF" stroke="{colour}" stroke-width="2.2"/>')
    s.text(x + 4, y + 7, str(number), 13, "bold", color="#222")
    cx = x + CARD_W / 2
    s.text(cx, y + 25, icon, 19, font=EMOJI)
    s.text(cx, y + 43, role, 10.5, "bold", color="#FFFFFF")
    s.text(cx, y + 62, title, 15, "bold", color="#FFFFFF")
    for i, row in enumerate(rows):
        s.text(cx, y + 81 + i * 16, row, 12.5, color="#FFFFFF")


def service(s, cx, y, w, kind, title, sub):
    """An AI model or external service above a step."""
    fill, stroke, icon = SERVICE[kind]
    s.raw(f'<rect x="{cx - w / 2}" y="{y}" width="{w}" height="40" rx="7" fill="{fill}" '
          f'stroke="{stroke}" stroke-width="1.2"/>')
    s.text(cx, y + 17, (icon + " " if icon else "") + title, 12.5, "bold", color="#7A4A00" if kind == "ai" else "#1F4F86")
    s.text(cx, y + 32, sub, 11, color="#555")


def store(s, cx, y, kind, w=112):
    """A data store below a step (cylinder)."""
    icon, name = STORE[kind]
    top = y + 8
    s.raw(
        f'<path d="M{cx - w / 2},{top} v26 a{w / 2},8 0 0 0 {w},0 v-26" fill="#FFFFFF" '
        f'stroke="#8E3B66" stroke-width="1.2"/>'
        f'<ellipse cx="{cx}" cy="{top}" rx="{w / 2}" ry="8" fill="#FFF3F8" stroke="#8E3B66" stroke-width="1.2"/>'
    )
    s.text(cx, top + 24, f"{icon} {name}", 12, "bold", color="#7A2E55", font=f"{EMOJI.split(',')[0]}, {FONT}")


def link(s, x, y1, y2, note=""):
    """A dashed data line between a step and a service or store (both ways)."""
    s.raw(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="#888" stroke-width="1.1" '
          f'stroke-dasharray="4 3" marker-start="url(#head)" marker-end="url(#head)"/>')
    if note:
        s.text(x + 6, (y1 + y2) / 2 + 4, note, 11, anchor="start", color="#666")


# Figure 2 draws a data store only where a step mainly depends on it.
STORES_SHOWN = {
    3: [("vec", "references")],  # RAG for the job description
    7: [("cv", "CV files")],  # the collector fills the CV folder
    11: [("db", "scores, ranking")],  # the shortlist reads it
    16: [("vec", "email template")],  # RAG for the invitation email
    20: [("vec", "question bank")],  # RAG in the interview room
    21: [("db", "transcript")],  # the analysis reads it
    23: [("vec", "documents")],  # RAG to check the answers
    24: [("db", "report")],  # reviewed, ranked, emailed from it
}


def fig2() -> Svg:
    """Every step of the process with its app part, AI model, external
    service and data store."""
    s = Svg(1800, 1930)
    s.text(24, 34, "CandiVue AI \u2014 Detailed System Workflow", 22, "bold", anchor="start")
    left = 225
    lanes = [
        ("1. Prepare", "the Job", "Hiring Assistant (LangGraph 1)", "#EAF4F2", [
            (1, "web", "\U0001F4AC", "WEB APP + API", "Open the job chat",
             ["POST /api/jobs, then messages", "to /api/assistant/jobs/{id}"], []),
            (2, "assistant", "\U0001F4DD", "HIRING ASSISTANT", "Describe the role",
             ["LLM asks questions, then", "save_job_profile + weights"],
             [("ai", "LLM (Gemini)", "chat + tool calls")]),
            (3, "assistant", "\U0001F50E", "HIRING ASSISTANT \u00B7 OPTIONAL", "Search references",
             ["rag_search when useful; also", "form link + closing date"],
             [("ai", "Embedding model", "Ollama, local")]),
            (4, "assistant", "\U0001F916", "HIRING ASSISTANT", "Write the job description",
             ["write_job_description:", "1 LLM request, draft card"],
             [("ai", "LLM (Gemini)", "JD writer")]),
            (5, "review", "\u2705", "HUMAN REVIEW \u00B7 INTERRUPT", "Approve, then \"Post?\"",
             ["approve / edit / reject, then", "Post / Don't post"], []),
            (6, "assistant", "\U0001F4E2", "HIRING ASSISTANT", "Post the job",
             ["post_to_job_board with the", "Google Form link"],
             [("ext", "Job board (Blogger)", "via MCP")]),
        ]),
        ("2. Collect and", "Screen CVs", "CV Collector + LangGraphs 2 and 5", "#FEF5E4", [
            (7, "service", "\U0001F4E5", "CV COLLECTOR SERVICE", "Collect applications",
             ["every 5 min: form answers", "+ CV files, read-only"],
             [("ext", "Google Form + Drive", "Sheets + Drive API")]),
            (8, "web", "\U0001F5C2\uFE0F", "WEB APP + API", "Start CV screening",
             ["Screen CVs button, POST", "/api/jobs/{id}/screenings"], []),
            (9, "workflow", "\U0001F4C4", "CV SCREENING (PARALLEL)", "Read each CV",
             ["text, OCR if scanned, parse,", "must-have gate (4 at a time)"],
             [("ext", "OCR (Tesseract)", "scanned CVs"), ("ai", "AI checks", "Gemini, else local")]),
            (10, "workflow", "\U0001F4CA", "CV SCREENING", "Score each CV",
             ["rules + local embeddings:", "4 scores, weighted 0-100"],
             [("ai", "Embedding model", "Ollama, local")]),
            (11, "workflow", "\U0001F3C6", "CV SCREENING", "Rank and save",
             ["ranking with reasons; GET", ".../screenings/latest"], []),
            (12, "workflow", "\U0001F501", "TALENT REDISCOVERY \u00B7 F11", "Check the talent pool",
             ["past applicants who opted in,", "same subgraph: suggestions"], []),
        ]),
        ("3. Invite", "Candidates", "Hiring Assistant (LangGraph 1)", "#EAF4F2", [
            (13, "assistant", "\U0001F4CB", "HIRING ASSISTANT", "Shortlist",
             ["update_shortlist: \"top 5\",", "\"above 75\" (applied in code)"],
             [("ai", "LLM (Gemini)", "words to criteria")]),
            (14, "assistant", "\U0001F4C5", "HIRING ASSISTANT", "Find times",
             ["find_free_slots,", "propose_invitations (checked)"],
             [("ext", "Calendar", "busy times via MCP")]),
            (15, "review", "\u2705", "HUMAN REVIEW \u00B7 INTERRUPT", "Confirm invitations",
             ["candidates, times, email", "preview; change or cancel"], []),
            (16, "assistant", "\U0001F4E7", "HIRING ASSISTANT", "Schedule and send",
             ["session + private link; email", "(template via RAG) + event"],
             [("ext", "Email (Gmail)", "via MCP"), ("ext", "Calendar", "via MCP")]),
        ]),
        ("4. Hold the", "Interview", "Real-time services + room assistant", "#ECF0F7", [
            (17, "web", "\U0001F511", "CANDIDATE PAGE", "Open the link",
             ["6-digit code by email, then", "a token for this interview"],
             [("ext", "Email (Gmail)", "via MCP")]),
            (18, "service", "\U0001F9D1", "IDENTITY CHECK \u00B7 F7", "Photo check-in",
             ["3 camera pictures vs. the form", "photo; result to interviewer"],
             [("ai", "Face models", "YuNet + SFace, local")]),
            (19, "service", "\U0001F3A5", "MEDIA SERVICE", "Waiting room, call",
             ["\"Let in\", LiveKit ticket; video,", "chat, auto-reconnect"],
             [("ext", "LiveKit", "WebRTC video server")]),
            (20, "assistant", "\U0001F4A1", "HIRING ASSISTANT \u00B7 ROOM", "Interview questions",
             ["question bank (RAG), questions", "from the CV, CV summary"],
             [("ai", "LLM (Gemini)", "question suggestions")]),
            (21, "service", "\U0001F399\uFE0F", "TRANSCRIPTION SERVICE", "Live transcript",
             ["one stream per speaker, with", "times; audio not stored"],
             [("ext", "Speech-to-text", "Deepgram, WebSocket")]),
            (22, "web", "\U0001F6D1", "WEB APP + API", "End the interview",
             ["POST /api/interviews/{id}/end", "starts LangGraph 3"], []),
        ]),
        ("5. Assess", "and Decide", "LangGraphs 3 and 4", "#F1EEF7", [
            (23, "workflow", "\U0001F50D", "Q&A ANALYSIS \u00B7 LANGGRAPH 3", "Analyse the answers",
             ["RAG for job + company answers;", "F8-F10; about 3 AI requests"],
             [("ai", "LLM + embeddings", "Gemini, Ollama")]),
            (24, "workflow", "\U0001F4CB", "FINAL ASSESSMENT \u00B7 LANGGRAPH 4", "Build the report",
             ["1 AI request; traceability", "check (max 2 repairs)"],
             [("ai", "LLM (Gemini)", "findings with evidence")]),
            (25, "review", "\u2705", "HUMAN REVIEW \u00B7 INTERRUPT", "Review the report",
             ["approve, or request changes", "with a comment"], []),
            (26, "web", "\U0001F3C6", "WEB APP + API", "Rank and compare",
             ["final ranking of approved", "reports; compare; PDF/HTML"], []),
            (27, "web", "\U0001F389", "WEB APP + API", "Selection email",
             ["editable text, preview,", "confirm, then send"],
             [("ext", "Email (Gmail)", "via MCP")]),
        ]),
    ]
    joins = ["Job posted with the Google Form link", "Ranked list saved",
             "At the scheduled time", "When the interview ends"]
    loops = {0: (4, 3, "rejected / edited"), 2: (2, 1, "cancelled: ask again"),
             4: (2, 1, "changes requested")}
    top, lane_h, gap = 56, 306, 22
    for i, (name1, name2, sub, fill, steps) in enumerate(lanes):
        y0 = top + i * (lane_h + gap)
        s.raw(f'<rect x="16" y="{y0}" width="1772" height="{lane_h}" rx="10" fill="{fill}"/>')
        s.text(30, y0 + 140, name1, 19, "bold", anchor="start")
        s.text(30, y0 + 163, name2, 19, "bold", anchor="start")
        s.text(30, y0 + 186, sub, 12.5, anchor="start", color="#555")
        card_y = y0 + 100
        for j, (number, kind, icon, role, title, rows, services) in enumerate(steps):
            stores = STORES_SHOWN.get(number, [])
            x = left + j * SLOT
            cx = x + CARD_W / 2
            step_card(s, x, card_y, number, kind, icon, role, title, *rows)
            if j:
                s.arrow([(x - SLOT + CARD_W, card_y + CARD_H / 2), (x, card_y + CARD_H / 2)])
            if services:
                w = CARD_W if len(services) == 1 else CARD_W / 2 - 4
                for k, (skind, stitle, ssub) in enumerate(services):
                    scx = cx if len(services) == 1 else x + w / 2 + k * (w + 8)
                    service(s, scx, y0 + 16, w, skind, stitle, ssub)
                    link(s, scx, y0 + 58, card_y)
            for k, (kind_, note) in enumerate(stores):
                n = len(stores)
                scx = cx if n == 1 else x + 56 + k * (CARD_W - 112)
                store(s, scx, card_y + CARD_H + 40, kind_, w=104 if n > 1 else 112)
                link(s, scx, card_y + CARD_H, card_y + CARD_H + 40, note)
        if i in loops:
            frm, to, note = loops[i]
            fx = left + frm * SLOT + CARD_W / 2
            tx = left + to * SLOT + CARD_W / 2 + 40
            s.arrow([(fx, card_y), (fx, card_y - 22), (tx, card_y - 22), (tx, card_y)],
                    dashed=True, label=note, at=((fx + tx) / 2, card_y - 22))
        if i < len(lanes) - 1:
            last = left + (len(steps) - 1) * SLOT + CARD_W
            mid = y0 + lane_h + gap / 2
            nxt = top + (i + 1) * (lane_h + gap) + 100
            s.arrow([(last, card_y + CARD_H / 2), (1772, card_y + CARD_H / 2), (1772, mid),
                     (left - 18, mid), (left - 18, nxt + CARD_H / 2), (left, nxt + CARD_H / 2)],
                    label=joins[i], at=(990, mid))

    # Legend.
    y = top + 5 * (lane_h + gap) + 16
    s.text(24, y, "Steps:", 14, "bold", anchor="start")
    x = 110
    for colour, name in KIND.values():
        s.raw(f'<rect x="{x}" y="{y - 12}" width="20" height="15" rx="3" fill="{colour}"/>')
        s.text(x + 27, y, name, 13.5, anchor="start")
        x += 48 + len(name) * 6.6
    y += 46
    s.text(24, y, "Parts:", 14, "bold", anchor="start")
    service(s, 175, y - 26, 120, "ai", "AI model", "Gemini or local")
    service(s, 320, y - 26, 140, "ext", "External service", "outside CandiVue")
    store(s, 470, y - 26, "db", w=120)
    store(s, 610, y - 26, "vec", w=130)
    store(s, 755, y - 26, "cv", w=120)
    s.text(830, y, "Database = PostgreSQL (+ LangGraph checkpoints) \u00B7 Vector store = pgvector \u00B7 CV folder = Docker volume",
           13, anchor="start", color="#444")
    y += 40
    for line in [
        "Lines: solid = next step; dashed with two heads = data read and written; dashed loop = back after a review.",
        "Data stores are drawn only where a step mainly depends on them; every step also saves its results in the "
        "Database (PostgreSQL).",
        "MCP servers (job board, email, calendar) hold their own credentials. The Hiring Assistant keeps one LangGraph "
        "thread per job (one per interview in the room);",
        "a review pauses the graph and resumes from the PostgreSQL checkpoint. LangGraphs 2-5 are started by the "
        "application, not by the chatbot.",
        "Candidates never see scores, rankings, transcripts or reports.",
    ]:
        s.text(24, y, line, 13.5, anchor="start", color="#444")
        y += 19
    s.caption("Figure 2: Detailed Architecture Diagram")
    return s


# ======================================================================
# Figure 3: LangGraph 1, Hiring Assistant (app/graphs/hiring_assistant.py)
# ======================================================================
def fig3() -> Svg:
    """The chatbot agent: tools, its three pauses and the guardrail."""
    s = Svg(1560, 960)
    s.terminal(560, 44, "START")
    s.node(445, 92, 230, 58, "blue", "load_context", "job, profile, latest JD, deadline")
    s.arrow([(560, 67), (560, 92)])
    s.arrow([(560, 150), (560, 186)])
    s.node(400, 186, 320, 84, "green", "assistant (LLM)",
           "chats with the interviewer and decides:", "reply, or call a tool", ai=1)

    # Guardrail and the normal reply (top right).
    s.node(930, 118, 210, 62, "orange", "off_topic", "fixed reply: ask about this job")
    s.terminal(1420, 238, "END")
    s.arrow([(720, 206), (840, 206), (840, 149), (930, 149)], dashed=True,
            label="only decline_off_topic", at=(840, 178))
    s.arrow([(1140, 149), (1420, 149), (1420, 215)])
    s.arrow([(720, 246), (1345, 246)], dashed=True, label="reply", at=(1240, 246))

    # Tools (job chat).
    s.group(30, 330, 690, 500, "tools (the LLM picks which one to call; RAG only if useful)")
    s.arrow([(560, 270), (560, 330)], dashed=True, label="LLM calls a tool", at=(560, 300))
    s.arrow([(270, 330), (270, 228), (400, 228)], label="result", at=(270, 280))

    def tool(col, row_y, title, note):
        """One tool box in the tools frame."""
        s.node(48 + col * 222, row_y, 208, 58, "blue", title, note)

    s.text(48, 384, "Job profile and description", 13.5, "bold", anchor="start", color="#666")
    tool(0, 392, "save_job_profile", "requirements + weights")
    tool(1, 392, "rag_search", "knowledge base (5 collections)")
    tool(2, 392, "write_job_description", "drafts the JD (AI x1)")
    s.text(48, 478, "Application", 13.5, "bold", anchor="start", color="#666")
    tool(0, 486, "save_application_form", "Google Form link")
    tool(1, 486, "set_application_deadline", "closing date and time")
    tool(2, 486, "request_job_posting", "asks \"Post?\" again")
    s.text(48, 572, "Shortlist and interviews", 13.5, "bold", anchor="start", color="#666")
    tool(0, 580, "update_shortlist", "\"top 5\", \"above 75\" (code)")
    tool(1, 580, "find_free_slots", "calendar busy times (MCP)")
    tool(2, 580, "propose_invitations", "checked plan + email preview")
    tool(0, 648, "reschedule_interview", "plan to move an interview")
    tool(1, 648, "cancel_interview", "plan to cancel one")
    s.text(48, 734, "Scope guardrail", 13.5, "bold", anchor="start", color="#666")
    s.node(48, 742, 430, 58, "orange", "decline_off_topic",
           "off-topic part declined; a job part in the same message goes on")

    # The three pauses (interrupts) and posting.
    s.node(800, 330, 190, 66, "purple", "human_review", "(interrupt) approve / edit / reject")
    s.node(1060, 330, 190, 66, "purple", "confirm_posting", "(interrupt) Post / Don't post")
    s.node(1320, 330, 200, 66, "blue", "post_to_job_board", "Blogger via MCP + form link")
    s.terminal(1420, 470, "END")
    s.arrow([(720, 352), (800, 352)], label="new JD", at=(760, 352))
    s.arrow([(990, 363), (1060, 363)], label="approve", at=(1025, 363))
    s.arrow([(1250, 363), (1320, 363)], label="Post", at=(1285, 363))
    s.arrow([(1420, 396), (1420, 447)])
    s.arrow([(1155, 396), (1155, 470), (1345, 470)], dashed=True,
            label="Don't post", at=(1250, 470))
    s.arrow([(895, 330), (895, 296), (700, 296), (700, 270)], dashed=True,
            label="reject: write a new version", at=(800, 296))
    s.arrow([(860, 396), (860, 428), (930, 428), (930, 398)], dashed=True,
            label="edit: new version", at=(895, 428))
    s.arrow([(720, 448), (1110, 448), (1110, 398)],
            label="request_job_posting", at=(1000, 448))

    s.node(800, 552, 400, 82, "purple", "confirm_invitations",
           "(interrupt) confirm, change times or cancel;",
           "on confirm: session + private link, invitation",
           "email (MCP) and calendar event (MCP)")
    s.arrow([(720, 593), (800, 593)], label="plan", at=(760, 593))
    s.terminal(1420, 593, "END")
    s.arrow([(1200, 593), (1345, 593)], label="saved or cancelled", at=(1272, 593))

    # Interview room mode.
    s.group(780, 680, 750, 150, "interview room mode: own thread per interview, no pauses",
            fill="#FAFAFA")
    for i, (title, note) in enumerate([
        ("search_question_bank", "question bank (RAG)"),
        ("questions_from_cv", "AI x1, saved"),
        ("candidate_summary", "CV without contacts"),
    ]):
        s.node(800 + i * 240, 724, 225, 58, "blue", title, note)
    s.text(800, 808, "also rag_search and decline_off_topic", 13.5, anchor="start", color="#555")

    s.text(780, 872, "One chat thread per job (assistant-job-<id>). A pause is a LangGraph interrupt saved in",
           14, anchor="start", color="#444")
    s.text(780, 890, "PostgreSQL; the API resumes it with the interviewer's decision. Nothing is posted or sent before that.",
           14, anchor="start", color="#444")
    s.caption("Figure 3: Hiring Assistant graph (chatbot agent, LangGraph 1)")
    return s


# ======================================================================
# Figure 4: LangGraph 2, CV Screening & Scoring (app/graphs/cv_screening.py)
# ======================================================================
def fig4() -> Svg:
    """The fixed screening workflow, one subgraph run per CV."""
    s = Svg(1150, 1372)
    cx = 520  # centre column
    s.terminal(cx, 44, "START")
    s.node(cx - 140, 92, 280, 50, "blue", "load_cv_batch", "the job's CVs, profile, weights")
    s.arrow([(cx, 67), (cx, 92)])
    s.group(24, 196, 1000, 800,
            "screen_cv (subgraph, once per CV in parallel, at most 4 at a time; reused in Figure 7)")
    s.arrow([(cx, 142), (cx, 236)], dashed=True, label="Send (one per CV)", at=(cx, 172))

    # Read the CV.
    s.node(cx - 140, 236, 280, 50, "blue", "extract_text", "text layer of the PDF / DOCX")
    s.node(760, 314, 210, 50, "orange", "ocr_extract", "scanned CV: Tesseract")
    s.arrow([(cx + 140, 266), (865, 266), (865, 314)], dashed=True, label="no text", at=(760, 266))
    s.node(cx - 140, 392, 280, 54, "green", "parse_cv", "sections, jobs, years, skills", bold=True)
    s.badge(cx + 134, 383, "AI check 1")
    s.arrow([(cx, 286), (cx, 392)], dashed=True, label="text found", at=(cx, 340))
    s.arrow([(865, 364), (865, 419), (cx + 140, 419)])
    s.arrow([(cx + 140, 246), (1000, 246), (1000, 470), (cx + 60, 470), (cx + 60, 497)],
            dashed=True, label="parsed before: reused", at=(1000, 300))

    # The must-have gate.
    s.diamond(cx, 520, 330, 92, "check_hard_requirements")
    s.badge(cx - 40, 470, "AI check 2")
    s.arrow([(cx, 446), (cx, 474)])
    s.node(40, 600, 190, 50, "orange", "log_and_skip", "unreadable CV")
    s.arrow([(cx - 140, 256), (70, 256), (70, 600)], dashed=True, label="error", at=(70, 430))
    s.arrow([(cx - 140, 432), (180, 432), (180, 600)], dashed=True)
    s.node(790, 600, 190, 50, "orange", "record_exclusion", "reason kept")
    s.arrow([(cx + 165, 520), (885, 520), (885, 600)], dashed=True, label="fail", at=(790, 520))

    # Match and score.
    s.node(cx - 150, 600, 300, 50, "green", "match_requirements", "met / partly / not met + evidence")
    s.arrow([(cx, 566), (cx, 600)], dashed=True, label="pass", at=(cx, 583))
    xs = [250, 435, 620, 805]
    for x, name in zip(xs, ["score_skills", "score_experience",
                            "score_qualifications", "ats_match"]):
        s.node(x - 85, 712, 170, 46, "green", name)
        s.arrow([(cx, 650), (cx, 681), (x, 681), (x, 712)])
    s.node(cx - 140, 830, 280, 60, "green", "combine_scores", "weights -> 0-100, with reasons", bold=True)
    for x in xs:
        s.arrow([(x, 758), (x, 795), (cx, 795), (cx, 830)])

    # After every CV.
    s.node(cx - 140, 1046, 280, 48, "blue", "collect_results")
    s.arrow([(cx, 890), (cx, 1046)])
    s.arrow([(56, 650), (56, 1070), (cx - 140, 1070)])
    s.arrow([(965, 650), (965, 1070), (cx + 140, 1070)])
    s.node(cx - 140, 1122, 280, 48, "blue", "rank_candidates", "excluded and unreadable not ranked")
    s.arrow([(cx, 1094), (cx, 1122)])
    s.node(cx - 140, 1198, 280, 48, "green", "save_results", "scores, ranking, reasons")
    s.arrow([(cx, 1170), (cx, 1198)])
    s.terminal(cx, 1280, "END")
    s.arrow([(cx, 1246), (cx, 1257)])
    s.note(cx + 180, 1201, 300, 42, "then: talent rediscovery starts (Figure 7)")
    s.arrow([(cx + 140, 1222), (cx + 180, 1222)], dashed=True)
    s.note(24, 1110, 330, 194,
           "Rules and local embeddings do the work.",
           "AI checks (Gemini first, local model as",
           "fallback), only when the rules cannot decide:",
           "1. no job dates: read the stated years",
           "2. must-have not found: read the CV once",
           "   more before excluding the candidate",
           "An answer counts only with a quote that is",
           "in the CV; name and contacts are removed",
           "first; answers are saved for later runs.", colour="orange")
    s.height = 1372
    s.caption("Figure 4: CV Screening & Scoring graph (LangGraph 2)")
    return s


# ======================================================================
# Figure 5: LangGraph 3, Interview Q&A Analysis (app/graphs/qa_analysis.py)
# ======================================================================
def fig5() -> Svg:
    """The fixed analysis workflow after the interview ends."""
    s = Svg(1100, 1290)
    cx = 470
    w = 400
    s.terminal(cx, 44, "START")
    steps = [
        ("blue", "load_transcript_and_requirements", ["job requirements; waits for the last words"], 0),
        ("green", "segment_qa_pairs", ["question-answer units, each job / company / other;",
                                       "checked against the transcript"], 1),
        ("blue", "retrieve_documents", ["local RAG per answer: job -> Reference library,",
                                        "company -> Company policies; other -> not scored"], 0),
    ]
    y = 96
    for colour, title, notes, ai in steps:
        h = 50 if len(notes) == 1 else 64
        s.node(cx - w / 2, y, w, h, colour, title, *notes, ai=ai)
        s.arrow([(cx, y - 28 if y == 96 else y - 30), (cx, y)])
        y += h + 30
    # y is now below retrieve_documents
    s.group(60, y + 30, 820, 170, "batches of up to 20 answers")
    s.arrow([(cx, y - 30), (cx, y + 66)], dashed=True, label="Send (one per batch)", at=(cx, y + 6))
    s.node(90, y + 66, 360, 72, "green", "evaluate_answers (batch 1)",
           "relevance, accuracy, completeness,", "articulation; cited lines + passages", ai=1)
    s.node(490, y + 66, 360, 72, "green", "evaluate_answers (batch 2 ...)",
           "only for long interviews", "(in parallel)", ai=1)
    after = y + 200
    s.node(cx - w / 2, after + 30, w, 50, "blue", "merge_evaluations", "units back in order")
    s.arrow([(270, y + 138), (270, after + 10), (cx, after + 10), (cx, after + 30)])
    s.arrow([(670, y + 138), (670, after + 10), (cx, after + 10)], head=False)
    s.arrow([(cx + w / 2, y - 60), (960, y - 60), (960, after + 55), (cx + w / 2, after + 55)],
            dashed=True, label="nothing to score", at=(960, y + 100))
    y = after + 110
    rest = [
        ("green", "map_to_requirements", ["each requirement with the units that explored it"], 0),
        ("blue", "find_unexplored_requirements", ["requirements never explored (gaps)"], 0),
        ("green", "review_interview", ["CV claims (F8); problem-solving and experience",
                                       "depth (F9); advice for the interviewer (F10)"], 1),
        ("green", "score_interview", ["F9: six dimensions with evidence (code)"], 0),
        ("green", "assess_interview_quality", ["F10: interview quality (code)"], 0),
        ("green", "save_qa_analysis", ["units, evaluations, coverage, F8-F10"], 0),
    ]
    prev = after + 80
    for colour, title, notes, ai in rest:
        h = 50 if len(notes) == 1 else 64
        s.node(cx - w / 2, y, w, h, colour, title, *notes, ai=ai)
        s.arrow([(cx, prev), (cx, y)])
        prev = y + h
        y += h + 30
    s.terminal(cx, y + 10, "END")
    s.arrow([(cx, prev), (cx, y - 13)])
    s.note(cx + 230, y - 12, 300, 46, "then: the final assessment starts", "(Figure 6)")
    s.arrow([(cx + 75, y + 10), (cx + 230, y + 10)], dashed=True)
    s.text(60, y + 66, "About 3 AI requests per interview (1 + one per 20 answers + 1). Names and contact details",
           14, anchor="start", color="#444")
    s.text(60, y + 84, "are removed from the transcript lines before they are sent; every AI answer is checked in code.",
           14, anchor="start", color="#444")
    s.height = y + 150
    s.caption("Figure 5: Interview Q&A Analysis graph (LangGraph 3)")
    return s


# ======================================================================
# Figure 6: LangGraph 4, Final Assessment (app/graphs/final_assessment.py)
# ======================================================================
def fig6() -> Svg:
    """The report, its traceability check and the interviewer's review."""
    s = Svg(1220, 1100)
    cx = 470
    s.terminal(cx, 44, "START")
    s.node(cx - 190, 92, 380, 64, "blue", "load_inputs",
           "CV, screening, Q&A analysis, CV claims,", "interview score and quality, identity check")
    s.arrow([(cx, 67), (cx, 92)])
    s.node(cx - 190, 196, 380, 64, "blue", "merge_scores",
           "CV score (F2) + interview score (F9)", "-> overall position (code)")
    s.arrow([(cx, 156), (cx, 196)])
    s.node(cx - 190, 300, 380, 64, "green", "write_findings",
           "strengths, weaknesses, evidence gaps,", "areas to verify; each cites evidence", ai=1)
    s.arrow([(cx, 260), (cx, 300)])
    s.node(cx - 190, 404, 380, 50, "blue", "build_report", "the report draft")
    s.arrow([(cx, 364), (cx, 404)])
    s.diamond(cx, 542, 340, 96, "check_traceability")
    s.arrow([(cx, 454), (cx, 494)])
    s.node(40, 517, 210, 50, "orange", "repair_findings", ai=1)
    s.arrow([(cx - 170, 542), (250, 542)], dashed=True)
    s.arrow([(145, 517), (145, 429), (cx - 190, 429)], label="missing evidence (max 2)", at=(175, 470))
    s.node(700, 640, 260, 60, "orange", "mark_unsupported_claims", "shown as unsupported")
    s.arrow([(cx + 170, 542), (830, 542), (830, 640)], dashed=True, label="retries used up", at=(760, 542))
    s.node(cx - 190, 760, 380, 70, "purple", "human_review",
           "(interrupt) the interviewer approves or", "requests changes with a comment")
    s.arrow([(cx, 590), (cx, 760)], dashed=True, label="all claims linked", at=(cx, 680))
    s.arrow([(830, 700), (830, 795), (cx + 190, 795)])
    s.arrow([(cx + 190, 815), (1060, 815), (1060, 228), (cx + 190, 228)], dashed=True,
            label="changes requested: next version", at=(1060, 420))
    s.node(cx - 190, 880, 380, 50, "green", "save_assessment", "approved report")
    s.arrow([(cx, 830), (cx, 880)], dashed=True, label="approved", at=(cx, 855))
    s.terminal(cx, 980, "END")
    s.arrow([(cx, 930), (cx, 957)])
    s.note(cx + 160, 958, 330, 46, "then (Reports page): final ranking,", "comparison, selection email")
    s.arrow([(cx + 75, 980), (cx + 160, 980)], dashed=True)
    s.text(40, 1040, "Every conclusion cites CV items, timestamped transcript lines or a requirement's coverage record;",
           14, anchor="start", color="#444")
    s.text(40, 1058, "cited ids are checked in code. The pause is saved in PostgreSQL until the interviewer reviews.",
           14, anchor="start", color="#444")
    s.height = 1110
    s.caption("Figure 6: Final Assessment graph (LangGraph 4)")
    return s


# ======================================================================
# Figure 7: Talent rediscovery, F11 (app/graphs/talent_rediscovery.py)
# ======================================================================
def fig7() -> Svg:
    """The talent pool screened against a job with Figure 4's subgraph."""
    s = Svg(1060, 800)
    cx = 450
    s.terminal(cx, 44, "START")
    s.note(640, 22, 380, 46, "starts after the job's screening,", "or on \"Check again\"")
    s.node(cx - 210, 96, 420, 82, "blue", "load_pool",
           "past applicants of other jobs who agreed to be",
           "considered; not in another process; at most",
           "365 days old; one (latest) application per person")
    s.arrow([(cx, 67), (cx, 96)])
    s.group(60, 220, 790, 200, "screen_cv (the subgraph of Figure 4, once per application, in parallel)")
    s.arrow([(cx, 178), (cx, 270)], dashed=True, label="Send (one per application)", at=(cx, 205))
    s.node(90, 270, 220, 64, "blue", "extract_text", "parsed CV reused")
    s.node(340, 270, 220, 64, "yellow", "check_hard_requirements", "the job's must-haves")
    s.node(590, 270, 230, 64, "green", "scores -> combine_scores", "the same scores as Figure 4")
    s.arrow([(310, 302), (340, 302)])
    s.arrow([(560, 302), (590, 302)])
    s.text(90, 368, "The same rules, embeddings and AI checks as screening. A CV read before is not parsed",
           14, anchor="start", color="#444")
    s.text(90, 386, "again; a must-have of this job the rules miss gets the AI second look (saved for later).",
           14, anchor="start", color="#444")
    s.text(90, 404, "Applications that fail a must-have are not matched.", 14, anchor="start", color="#444")
    s.node(cx - 160, 470, 320, 50, "blue", "collect_results")
    s.arrow([(cx, 420), (cx, 470)])
    s.node(cx - 210, 560, 420, 64, "green", "save_matches",
           "passes the must-haves and reaches the minimum", "score; kept apart from the job's own ranking")
    s.arrow([(cx, 520), (cx, 560)])
    s.terminal(cx, 674, "END")
    s.arrow([(cx, 624), (cx, 651)])
    s.note(cx + 120, 692, 470, 46, "then: the interviewer may click \"Add to this job\"",
           "(the CV is copied; normal screening and steps follow)")
    s.arrow([(cx + 75, 674), (cx + 120, 715)], dashed=True)
    s.caption("Figure 7: Talent Rediscovery graph (LangGraph 5, F11 innovation feature)")
    return s


FIGURES = {
    "fig1": ("high_level_system_diagram", fig1),
    "fig2": ("detailed_architecture_diagram", fig2),
    "fig3": ("langgraph_1_hiring_assistant", fig3),
    "fig4": ("langgraph_2_cv_screening", fig4),
    "fig5": ("langgraph_3_qa_analysis", fig5),
    "fig6": ("langgraph_4_final_assessment", fig6),
    "fig7": ("langgraph_5_talent_rediscovery", fig7),
}


def edge() -> Path:
    """The Microsoft Edge program (it prints the pages to PDF)."""
    for path in EDGE:
        if path.exists():
            return path
    raise SystemExit("Microsoft Edge was not found; it is needed to print the PDFs.")


def render(name: str, drawing: Svg, browser: Path) -> None:
    """Write the HTML page (build folder; open it in a browser to look at
    the figure) and print it to docs/diagrams/<name>.pdf."""
    BUILD.mkdir(exist_ok=True)
    page = BUILD / f"{name}.html"
    w, h = drawing.width, drawing.height
    page.write_text(
        "<!doctype html><meta charset='utf-8'><style>"
        f"@page {{ size: {w}px {h}px; margin: 0 }} html, body {{ margin: 0 }}"
        f"svg {{ display: block }}</style>{drawing.write()}",
        encoding="utf-8",
    )
    # Its own profile, so an open Edge window is never used or disturbed.
    common = [str(browser), "--headless=new", "--disable-gpu", "--hide-scrollbars",
              f"--user-data-dir={BUILD / 'edge-profile'}"]
    subprocess.run(
        [*common, "--no-pdf-header-footer", f"--print-to-pdf={OUT / (name + '.pdf')}",
         page.as_uri()],
        check=True, capture_output=True,
    )
    print(f"{name}.pdf ({w} x {h})")


if __name__ == "__main__":
    chosen = sys.argv[1:] or list(FIGURES)
    browser = edge()
    for key in chosen:
        filename, make = FIGURES[key]
        render(filename, make(), browser)
