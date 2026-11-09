"""The Clinical desktop interface. Tk is used only for presentation, not storage."""

from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .chain import CheckStep, VerificationReport
from .records import MedicalRecord
from .service import MedKeepService
from .structures import LinkedSequence

BG = "#F3F6F5"
WHITE = "#FFFFFF"
INK = "#173333"
MUTED = "#60746F"
LINE = "#DCE5E1"
TEAL = "#14695B"
SOFT = "#E7F1EC"
RED = "#A13844"
BODY = ("Segoe UI", 10)
SMALL = ("Segoe UI", 9)


def label(parent, text="", *, bg=BG, fg=INK, font=BODY, **options):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, anchor="w", **options)


def card(parent, *, bg=WHITE, padding=22):
    return tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1,
                    padx=padding, pady=padding)


class ScrollPage(ttk.Frame):
    """A page expands to the available width and scrolls on smaller displays."""

    def __init__(self, parent):
        super().__init__(parent, style="Page.TFrame")
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, borderwidth=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview, style="Clinical.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=BG, padx=28, pady=25)
        self.body.columnconfigure(0, weight=1)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", self._body_changed)
        self.canvas.bind("<Configure>", self._canvas_changed)

    def _body_changed(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _canvas_changed(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)


class _Job:
    """One worker's result slot. There is no library queue between UI and worker."""

    def __init__(self, action: Callable):
        self.result = None
        self.error: Exception | None = None
        self.thread = threading.Thread(target=self._execute, args=(action,), daemon=False)

    def _execute(self, action):
        try:
            self.result = action()
        except Exception as error:
            self.error = error


class MedKeepApp:
    def __init__(self, root: tk.Tk, service: MedKeepService):
        self.root, self.service = root, service
        self._controls: LinkedSequence[tk.Widget] = LinkedSequence()
        self._job: _Job | None = None
        self._closing = False
        self.closed = False
        self.last_error: Exception | None = None
        self.last_archive: Path | None = None
        self._history_records: LinkedSequence[MedicalRecord] = LinkedSequence()
        self._steps: LinkedSequence[CheckStep] = LinkedSequence()
        self.status = tk.StringVar(value="Ready. Requests are saved automatically.")
        self.patient = tk.StringVar()
        self.author = tk.StringVar()
        self.visit_date = tk.StringVar(value=date.today().isoformat())
        self.record_title = tk.StringVar()
        self.preview_patient = tk.StringVar(value="PATIENT REFERENCE")
        self.preview_author = tk.StringVar(value="Not entered")
        self.preview_date = tk.StringVar(value=date.today().isoformat())
        self.preview_title = tk.StringVar(value="Your next record starts here.")
        self.preview_notes = tk.StringVar(value="A preview of your notes will appear here as you write.")
        self.note_count = tk.StringVar(value="0 / 6000 characters")
        self.history_search = tk.StringVar()
        self.archive_date = tk.StringVar(value=date.today().isoformat())
        root.title("MedKeep")
        root.configure(bg=BG)
        self.display_scale = max(1.0, root.winfo_fpixels("1i") / 96)
        width = min(round(1240 * self.display_scale), root.winfo_screenwidth() - round(60 * self.display_scale))
        height = min(round(900 * self.display_scale), root.winfo_screenheight() - round(90 * self.display_scale))
        root.geometry(f"{width}x{height}")
        root.minsize(min(round(1000 * self.display_scale), width), min(round(680 * self.display_scale), height))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._header()
        self._footer()
        self.tabs = ttk.Notebook(root, style="Clinical.TNotebook")
        self.tabs.pack(fill="both", expand=True)
        self.create_page = ScrollPage(self.tabs)
        self.approval_page = ScrollPage(self.tabs)
        self.queue_page = ScrollPage(self.tabs)
        self.history_page = ScrollPage(self.tabs)
        self.tabs.add(self.create_page, text="Create")
        self.tabs.add(self.approval_page, text="Approval")
        self.tabs.add(self.queue_page, text="Queue  0")
        self.tabs.add(self.history_page, text="History")
        self._create_section()
        self._approval_section()
        self._queue_section()
        self._history_section()
        self.tabs.bind("<<NotebookTabChanged>>", self._tab_changed)
        root.bind_all("<MouseWheel>", self._wheel, add="+")
        root.bind_all("<Button-4>", lambda event: self._wheel(event, -1), add="+")
        root.bind_all("<Button-5>", lambda event: self._wheel(event, 1), add="+")
        root.bind("<Control-Return>", self._shortcut_submit)
        root.bind("<F5>", lambda _event: self.verify())
        for index in range(4):
            root.bind(f"<Control-Key-{index + 1}>", lambda _event, i=index: self.tabs.select(i))
        for variable in (self.patient, self.author, self.visit_date, self.record_title):
            variable.trace_add("write", self._preview)
        self.history_search.trace_add("write", self._filter_history)
        self._refresh()

    @property
    def busy(self):
        return self._job is not None

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", font=BODY)
        style.configure("Page.TFrame", background=BG)
        style.configure("Clinical.TNotebook", background=WHITE, borderwidth=0, tabmargins=(28, 10, 0, 0))
        style.configure("Clinical.TNotebook.Tab", background=WHITE, foreground=MUTED,
                        borderwidth=0, padding=(23, 13), font=("Segoe UI", 10))
        self._tab_plain = tk.PhotoImage(width=2, height=5)
        self._tab_plain.put(WHITE, to=(0, 0, 2, 5))
        self._tab_plain.put(LINE, to=(0, 4, 2, 5))
        self._tab_selected = tk.PhotoImage(width=2, height=5)
        self._tab_selected.put(SOFT, to=(0, 0, 2, 5))
        self._tab_selected.put(TEAL, to=(0, 2, 2, 5))
        style.element_create("Clinical.tab", "image", self._tab_plain,
                             ("selected", self._tab_selected), border=(0, 0, 0, 3), sticky="nsew")
        style.layout("Clinical.TNotebook.Tab", [("Clinical.tab", {"sticky": "nswe", "children": [
            ("Notebook.padding", {"sticky": "nswe", "children": [("Notebook.label", {"sticky": "nswe"})]})]})])
        style.map("Clinical.TNotebook.Tab", foreground=[("selected", TEAL)],
                  padding=[("selected", (23, 13)), ("!selected", (23, 13))],
                  expand=[("selected", (0, 0, 0, 0))])
        style.configure("Primary.TButton", background=TEAL, foreground=WHITE, padding=(17, 11),
                        borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("Primary.TButton", background=[("disabled", "#C9D6D1"), ("active", "#0E574B")],
                  foreground=[("disabled", "#596E67")])
        style.configure("Secondary.TButton", background=WHITE, foreground=INK, padding=(14, 10),
                        borderwidth=1, bordercolor=LINE)
        style.map("Secondary.TButton", background=[("active", SOFT), ("disabled", BG)], foreground=[("disabled", MUTED)])
        style.configure("Clinical.TEntry", padding=(10, 9), fieldbackground=WHITE,
                        foreground=INK, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.map("Clinical.TEntry", bordercolor=[("focus", TEAL)])
        style.configure("Clinical.Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK,
                        rowheight=42, borderwidth=0, font=BODY)
        style.configure("Clinical.Treeview.Heading", background=WHITE, foreground=MUTED,
                        font=("Segoe UI", 9), padding=(9, 12), borderwidth=0)
        style.map("Clinical.Treeview", background=[("selected", SOFT)], foreground=[("selected", TEAL)])
        style.configure("Clinical.Horizontal.TProgressbar", background=TEAL, troughcolor=SOFT, borderwidth=0)
        style.configure("Clinical.Vertical.TScrollbar", background=LINE, troughcolor=BG, borderwidth=0,
                        arrowsize=10, width=10)
        style.layout("Clinical.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky":"ns", "children":[
            ("Vertical.Scrollbar.thumb", {"sticky":"nswe"})]})])

    def _header(self):
        header = tk.Frame(self.root, bg=WHITE, padx=29, pady=20)
        header.pack(fill="x")
        mark = tk.Canvas(header, width=37, height=37, bg=WHITE, highlightthickness=0)
        mark.pack(side="left", padx=(0, 12))
        mark.create_oval(0, 0, 37, 37, fill=TEAL, outline=TEAL)
        mark.create_line(18, 10, 18, 27, fill=WHITE, width=2)
        mark.create_line(10, 18, 27, 18, fill=WHITE, width=2)
        wordmark = tk.Frame(header, bg=WHITE)
        wordmark.pack(side="left")
        label(wordmark, "MedKeep", bg=WHITE, font=("Segoe UI", 17, "bold")).pack(anchor="w")
        label(wordmark, "R E C O R D S ,  K E P T  W I T H  C A R E .", bg=WHITE, fg=MUTED,
              font=("Segoe UI", 7)).pack(anchor="w")
        label(header, "●  Offline workspace", bg=SOFT, fg=TEAL, font=SMALL, padx=14, pady=7).pack(side="right")
        tk.Frame(self.root, bg=LINE, height=1).pack(fill="x")

    def _footer(self):
        footer = tk.Frame(self.root, bg=BG, padx=29, pady=11)
        footer.pack(side="bottom", fill="x")
        self.status_label = label(footer, textvariable=self.status, fg=MUTED, font=SMALL, wraplength=780)
        self.status_label.pack(side="left")
        self.progress = ttk.Progressbar(footer, mode="indeterminate", length=100,
                                       style="Clinical.Horizontal.TProgressbar")
        self.saved_label = label(footer, "Saved locally", fg=MUTED, font=SMALL)
        self.saved_label.pack(side="right")

    def _hero(self, page, eyebrow, title, subtitle):
        top = tk.Frame(page.body, bg=BG)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 23))
        top.columnconfigure(0, weight=1)
        label(top, eyebrow.upper(), fg=TEAL, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        label(top, title, font=("Segoe UI", 23, "bold")).grid(row=1, column=0, sticky="w")
        label(top, subtitle, fg=MUTED, font=SMALL).grid(row=2, column=0, sticky="w", pady=(8, 0))
        label(top, datetime.now().strftime("%d %b %Y"), fg=MUTED, font=SMALL).grid(row=0, column=1, sticky="e")

    def _button(self, parent, text, command, primary=False):
        button = ttk.Button(parent, text=text, command=command,
                            style="Primary.TButton" if primary else "Secondary.TButton")
        self._controls.append(button)
        return button

    def _field(self, parent, text, variable, row, column, *, background=WHITE, width=25):
        field = tk.Frame(parent, bg=background)
        field.grid(row=row, column=column, sticky="ew", padx=(0, 9) if column == 0 else (9, 0), pady=(0, 17))
        label(field, text, bg=background, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 7))
        entry = ttk.Entry(field, textvariable=variable, style="Clinical.TEntry", width=width)
        entry.pack(fill="x")
        self._controls.append(entry)
        return entry

    def _create_section(self):
        page = self.create_page
        self._hero(page, "New record request", "A little clarity. A better record.",
                   "Prepare an entry and send it to the processing queue.")
        columns = tk.Frame(page.body, bg=BG)
        columns.grid(row=1, column=0, sticky="ew")
        columns.columnconfigure(0, weight=3, minsize=490)
        columns.columnconfigure(1, weight=2, minsize=285)
        form = card(columns)
        form.grid(row=0, column=0, sticky="new", padx=(0, 20))
        label(form, "Record details", bg=WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 22))
        fields = tk.Frame(form, bg=WHITE)
        fields.pack(fill="x")
        fields.columnconfigure(0, weight=1)
        fields.columnconfigure(1, weight=1)
        self.patient_entry = self._field(fields, "Patient reference", self.patient, 0, 0)
        self._field(fields, "Recorded by", self.author, 0, 1)
        self._field(fields, "Visit date · YYYY-MM-DD", self.visit_date, 1, 0)
        self._field(fields, "Record title", self.record_title, 1, 1)
        label(form, "Clinical notes", bg=WHITE, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 7))
        note_frame = tk.Frame(form, bg=WHITE, highlightbackground=LINE, highlightthickness=1)
        note_frame.pack(fill="both", expand=True)
        self.notes = tk.Text(note_frame, height=7, width=1, wrap="word", font=BODY, relief="flat",
                             bg=WHITE, fg=INK, padx=11, pady=10, undo=True, insertbackground=TEAL)
        note_scroll = ttk.Scrollbar(note_frame, command=self.notes.yview, style="Clinical.Vertical.TScrollbar")
        self.notes.configure(yscrollcommand=note_scroll.set)
        note_scroll.pack(side="right", fill="y")
        self.notes.pack(side="left", fill="both", expand=True)
        self._controls.append(self.notes)
        self.notes.bind("<<Modified>>", self._notes_changed)
        self.notes.bind("<Control-a>", self._select_all_notes)
        self.notes.bind("<Control-A>", self._select_all_notes)
        label(form, textvariable=self.note_count, bg=WHITE, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(7, 0))
        actions = tk.Frame(form, bg=WHITE)
        actions.pack(fill="x", pady=(21, 0))
        self._button(actions, "Clear form", self.clear_form).pack(side="left")
        self._button(actions, "Add to queue  →", self.enqueue, primary=True).pack(side="right")
        summary = card(columns, bg=SOFT, padding=22)
        summary.grid(row=0, column=1, sticky="new")
        line = tk.Frame(summary, bg=SOFT)
        line.pack(fill="x", pady=(0, 25))
        label(line, "R E Q U E S T  P R E V I E W", bg=SOFT, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        label(line, "Draft", bg=SOFT, fg=MUTED, font=("Segoe UI", 8)).pack(side="right")
        label(summary, textvariable=self.preview_patient, bg=SOFT, fg=MUTED, font=SMALL,
              wraplength=290, justify="left").pack(anchor="w")
        label(summary, textvariable=self.preview_title, bg=SOFT, font=("Segoe UI", 16, "bold"),
              wraplength=290, justify="left").pack(anchor="w", pady=(7, 21))
        self._summary_line(summary, "Recorded by", self.preview_author)
        self._summary_line(summary, "Visit date", self.preview_date)
        self._summary_line(summary, "Destination", "FIFO queue")
        label(summary, textvariable=self.preview_notes, bg=SOFT, wraplength=290, justify="left",
              font=SMALL).pack(anchor="w", pady=(18, 25))
        label(summary, "Create  →  Queue  →  Chain  →  Verify", bg=SOFT, fg=TEAL,
              font=("Segoe UI", 8)).pack(anchor="w")
        label(page.body, "Ctrl+Enter to enqueue   ·   Your draft stays here until the save succeeds.",
              fg=MUTED, font=("Segoe UI", 8)).grid(row=2, column=0, sticky="w", pady=(16, 0))

    def _summary_line(self, parent, text, value):
        row = tk.Frame(parent, bg=parent["bg"])
        row.pack(fill="x", pady=(0, 0))
        row.columnconfigure(1, weight=1)
        label(row, text, bg=parent["bg"], fg=MUTED, font=SMALL).grid(row=0, column=0, sticky="w", pady=10)
        options = {"textvariable": value} if isinstance(value, tk.Variable) else {"text": value}
        label(row, bg=parent["bg"], font=SMALL, wraplength=180, justify="right", **options).grid(row=0, column=1, sticky="e", padx=(10, 0), pady=10)
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x")

    def _tree(self, parent, columns, headings, widths, height=7):
        shell = tk.Frame(parent, bg=WHITE)
        shell.pack(fill="both", expand=True)
        tree = ttk.Treeview(shell, columns=columns, show="headings", selectmode="browse",
                            style="Clinical.Treeview", height=height)
        for name, heading, width in zip(columns, headings, widths):
            tree.heading(name, text=heading, anchor="w")
            tree.column(name, width=width, minwidth=45, stretch=True, anchor="w")
        scroll = ttk.Scrollbar(shell, command=tree.yview, style="Clinical.Vertical.TScrollbar")
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _approval_section(self):
        page = self.approval_page
        self._hero(page, "Integrity approval", "Check the chain.",
                   "Compare stored and recalculated hashes before reading record history.")
        state = card(page.body, bg=SOFT, padding=19)
        state.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        self.approval_title = label(state, "Ready for an integrity check", bg=SOFT, fg=TEAL, font=("Segoe UI", 13, "bold"))
        self.approval_title.pack(anchor="w")
        self.approval_message = label(state, "The chain has not been checked in this session.", bg=SOFT, fg=MUTED,
                                      wraplength=950, justify="left", font=SMALL)
        self.approval_message.pack(anchor="w", pady=(6, 0))
        columns = tk.Frame(page.body, bg=BG)
        columns.grid(row=2, column=0, sticky="ew")
        columns.columnconfigure(0, weight=3)
        columns.columnconfigure(1, weight=2)
        checks = card(columns)
        checks.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        label(checks, "Step-by-step verification", bg=WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 12))
        self.check_tree = self._tree(checks, ("node", "kind", "result"), ("Node", "Type", "Result"), (75, 100, 150), height=6)
        self.check_tree.bind("<<TreeviewSelect>>", self._select_step)
        detail = card(columns)
        detail.grid(row=0, column=1, sticky="nsew")
        label(detail, "Selected check", bg=WHITE, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 17))
        self.step_description = label(detail, "Run verification to inspect the chain.", bg=WHITE, fg=MUTED,
                                      wraplength=310, justify="left", font=SMALL)
        self.step_description.pack(anchor="w", pady=(0, 16))
        label(detail, "Stored hash", bg=WHITE, fg=MUTED, font=SMALL).pack(anchor="w")
        self.stored_hash = label(detail, "—", bg=WHITE, font=("Consolas", 9), wraplength=310, justify="left")
        self.stored_hash.pack(anchor="w", pady=(5, 18))
        label(detail, "Recalculated hash", bg=WHITE, fg=MUTED, font=SMALL).pack(anchor="w")
        self.calculated_hash = label(detail, "—", bg=WHITE, font=("Consolas", 9), wraplength=310, justify="left")
        self.calculated_hash.pack(anchor="w", pady=(5, 16))
        label(detail, "SHA-256 · implemented by hand", bg=WHITE, fg=TEAL, font=("Segoe UI", 8)).pack(anchor="w")
        actions = tk.Frame(page.body, bg=BG)
        actions.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        self._button(actions, "Verify integrity", self.verify, primary=True).pack(side="left")
        self._button(actions, "Open history  →", lambda: self.tabs.select(self.history_page)).pack(side="left", padx=10)
        label(page.body, "Approval checks integrity. It does not represent a clinical sign-off.", fg=MUTED,
              font=("Segoe UI", 8)).grid(row=4, column=0, sticky="w", pady=(16, 0))

    def _queue_section(self):
        page = self.queue_page
        self._hero(page, "Request processing", "First in. First recorded.",
                   "The oldest request is always processed first, regardless of the selected row.")
        panel = card(page.body)
        panel.grid(row=1, column=0, sticky="ew")
        self.queue_count_label = label(panel, "No requests waiting", bg=WHITE, font=("Segoe UI", 12, "bold"))
        self.queue_count_label.pack(anchor="w", pady=(0, 13))
        self.queue_tree = self._tree(panel, ("position", "request", "patient", "title", "received"),
                                     ("Order", "Request", "Patient", "Record title", "Received"),
                                     (55, 130, 110, 260, 180), height=6)
        self.queue_tree.bind("<<TreeviewSelect>>", self._select_pending)
        actions = tk.Frame(panel, bg=WHITE)
        actions.pack(fill="x", pady=(18, 0))
        label(actions, "Each request creates a content node and its seal.", bg=WHITE, fg=MUTED, font=SMALL).pack(side="left")
        self.process_button = self._button(actions, "Process oldest  →", self.process_next, primary=True)
        self.process_button.pack(side="right")
        detail = card(page.body, bg=SOFT, padding=19)
        detail.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        self.pending_title = label(detail, "The queue is clear.", bg=SOFT, font=("Segoe UI", 12, "bold"), wraplength=950, justify="left")
        self.pending_title.pack(anchor="w")
        self.pending_meta = label(detail, "New requests will appear here after you save them in Create.", bg=SOFT, fg=MUTED, font=SMALL, wraplength=950, justify="left")
        self.pending_meta.pack(anchor="w", pady=(6, 9))
        self.pending_notes = label(detail, "", bg=SOFT, wraplength=950, justify="left", font=SMALL)
        self.pending_notes.pack(anchor="w")

    def _history_section(self):
        page = self.history_page
        self._hero(page, "Verified record history", "A record you can follow.",
                   "Review verified entries and prepare a daily archive. Sealed records are read-only.")
        self.history_gate = card(page.body, padding=27)
        self.history_gate.grid(row=1, column=0, sticky="ew")
        label(self.history_gate, "Verification comes first", bg=WHITE, font=("Segoe UI", 14, "bold")).pack(anchor="w")
        self.gate_message = label(self.history_gate, "Run the integrity check in Approval to open record history.", bg=WHITE, fg=MUTED,
                                  wraplength=900, justify="left", font=BODY)
        self.gate_message.pack(anchor="w", pady=(10, 19))
        self._button(self.history_gate, "Go to Approval  →", lambda: self.tabs.select(self.approval_page), primary=True).pack(anchor="w")
        self.history_content = tk.Frame(page.body, bg=BG)
        self.history_content.grid(row=1, column=0, sticky="ew")
        searchbar = tk.Frame(self.history_content, bg=BG)
        searchbar.pack(fill="x", pady=(0, 15))
        label(searchbar, "Find a record", fg=MUTED, font=SMALL).pack(side="left", padx=(0, 12))
        self.search_entry = ttk.Entry(searchbar, textvariable=self.history_search, style="Clinical.TEntry", width=38)
        self.search_entry.pack(side="left")
        label(searchbar, "Patient, title or request number", fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=12)
        panel = card(self.history_content)
        panel.pack(fill="x")
        self.history_count = label(panel, "No records yet", bg=WHITE, font=("Segoe UI", 12, "bold"))
        self.history_count.pack(anchor="w", pady=(0, 13))
        self.history_tree = self._tree(panel, ("request", "patient", "title", "processed"),
                                       ("Request", "Patient", "Record title", "Processed"),
                                       (140, 120, 320, 210), height=4)
        self.history_tree.bind("<<TreeviewSelect>>", self._select_history)
        detail = card(self.history_content, bg=SOFT, padding=19)
        detail.pack(fill="x", pady=17)
        self.history_title = label(detail, "Select a verified record", bg=SOFT, font=("Segoe UI", 12, "bold"), wraplength=950, justify="left")
        self.history_title.pack(anchor="w")
        self.history_meta = label(detail, "", bg=SOFT, fg=MUTED, font=SMALL, wraplength=950, justify="left")
        self.history_meta.pack(anchor="w", pady=(6, 10))
        self.history_notes = tk.Text(detail, height=3, width=1, wrap="word", font=BODY, bg=SOFT, fg=INK,
                                     relief="flat", borderwidth=0, state="disabled", padx=0, pady=0)
        self.history_notes.pack(fill="x")
        archive = tk.Frame(self.history_content, bg=BG)
        archive.pack(fill="x", before=panel, pady=(0, 14))
        label(archive, "Processed date", fg=MUTED, font=SMALL).pack(side="left", padx=(0, 12))
        archive_entry = ttk.Entry(archive, textvariable=self.archive_date, style="Clinical.TEntry", width=13)
        archive_entry.pack(side="left", padx=(0, 12))
        self._controls.append(archive_entry)
        self.archive_button = self._button(archive, "Export daily archive", self.export_archive, primary=True)
        self.archive_button.pack(side="left")
        self.open_archive_button = self._button(archive, "Open last archive", self.open_archive)
        self.open_archive_button.pack(side="left", padx=10)
        label(self.history_content, "Archives are saved in the workspace's archives folder. Original records stay in the chain.",
              fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", before=panel, pady=(0, 14))
        self.history_content.grid_remove()

    def _select_all_notes(self, _event):
        self.notes.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _notes_changed(self, _event=None):
        if self.notes.edit_modified():
            self.notes.edit_modified(False)
            self._preview()

    def _preview(self, *_args):
        self.preview_patient.set(self.patient.get().strip() or "PATIENT REFERENCE")
        self.preview_author.set(self.author.get().strip() or "Not entered")
        self.preview_date.set(self.visit_date.get().strip() or "Not entered")
        self.preview_title.set(self.record_title.get().strip() or "Your next record starts here.")
        notes = self.notes.get("1.0", "end-1c")
        self.note_count.set(f"{len(notes)} / 6000 characters")
        self.preview_notes.set((notes[:300] + ("…" if len(notes) > 300 else "")) or "A preview of your notes will appear here as you write.")

    def clear_form(self):
        if self.busy:
            return
        self.patient.set("")
        self.record_title.set("")
        self.notes.delete("1.0", "end")
        self._preview()
        self.patient_entry.focus_set()

    def _shortcut_submit(self, _event):
        if self.tabs.index("current") == 0:
            self.enqueue()
        return "break"

    def enqueue(self):
        if self.busy:
            return
        patient, author = self.patient.get(), self.author.get()
        day, title, notes = self.visit_date.get().strip(), self.record_title.get(), self.notes.get("1.0", "end-1c")
        self._run_job(lambda: self.service.enqueue(patient, author, day, title, notes), self._enqueued, "Saving request…")

    def _enqueued(self, record):
        self.clear_form()
        self._set_status(f"{record.reference} saved. Queue position: {self.service.pending_count}.")

    def process_next(self):
        if self.busy or not self.service.pending_count:
            return
        self._run_job(self.service.process_next, self._processed, "Processing the oldest request…")

    def _processed(self, record):
        self._set_status(f"{record.reference} recorded with its seal. Open Approval to verify the updated chain.")

    def verify(self):
        if self.busy:
            return
        self._run_job(self.service.verify, self._verified, "Verifying the chain…")

    def _verified(self, report):
        self._display_report(report)
        self._set_status(report.message, error=not report.ok)

    def export_archive(self):
        if self.busy:
            return
        day = self.archive_date.get().strip()
        self._run_job(lambda: self.service.archive(day), self._archived, "Verifying and exporting the daily archive…")

    def _archived(self, path):
        self.last_archive = path
        self._set_status(f"Archive saved: {path.name}")

    def open_archive(self):
        if self.last_archive is None or not self.last_archive.exists():
            self._set_status("Export a daily archive first.", error=True)
            return
        try:
            if sys.platform == "win32":
                os.startfile(self.last_archive)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.last_archive)])
        except OSError:
            self._set_status(f"Open this archive from your workspace: {self.last_archive.name}", error=True)

    def _run_job(self, action, on_success, message):
        if self.busy or self._closing:
            return
        self.last_error = None
        self._job = _Job(action)
        self._set_status(message)
        self._update_controls()
        self.saved_label.pack_forget()
        self.progress.pack(side="right", padx=(12, 0))
        self.progress.start(12)
        self._job.thread.start()
        self.root.after(50, lambda: self._poll(on_success))

    def _poll(self, on_success):
        job = self._job
        if job is None:
            return
        if job.thread.is_alive():
            self.root.after(50, lambda: self._poll(on_success))
            return
        self._job = None
        self.progress.stop()
        self.progress.pack_forget()
        self.saved_label.pack(side="right")
        self._update_controls()
        if job.error is not None:
            self.last_error = job.error
            if isinstance(job.error, (ValueError, IndexError, OSError)):
                self._set_status(str(job.error), error=True)
            else:
                self._set_status("An unexpected error prevented this operation. Saved data was kept.", error=True)
        else:
            on_success(job.result)
        self._refresh()
        if self._closing:
            self._shutdown()

    def _set_status(self, message, error=False):
        self.status.set(message)
        self.status_label.configure(fg=RED if error else TEAL)

    def _refresh(self):
        self.tabs.tab(self.queue_page, text=f"Queue  {self.service.pending_count}")
        self.queue_count_label.configure(text=f"{self.service.pending_count} request(s) waiting" if self.service.pending_count else "All clear. No requests waiting.")
        selection = self.queue_tree.selection()
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for index, record in enumerate(self.service.pending(), 1):
            self.queue_tree.insert("", "end", iid=str(record.request_id), values=(f"{index:02d}", record.reference, record.patient,
                                   record.title, record.submitted_at[:16].replace("T", " ")))
        children = self.queue_tree.get_children()
        if children:
            self.queue_tree.selection_set(selection[0] if selection and selection[0] in children else children[0])
            self._select_pending()
        else:
            self.pending_title.configure(text="The queue is clear.")
            self.pending_meta.configure(text="New requests appear here after you save them in Create.")
            self.pending_notes.configure(text="")
        report = self.service.report
        if report is None:
            self.approval_title.configure(text="Ready for an integrity check", fg=TEAL)
            self.approval_message.configure(text=f"{self.service.record_count} record(s) · {self.service.node_count} node(s). Verify the current workspace to open History.")
            self._steps = LinkedSequence()
            for item in self.check_tree.get_children():
                self.check_tree.delete(item)
            self.stored_hash.configure(text="—")
            self.calculated_hash.configure(text="—")
            self.step_description.configure(text="Run verification to inspect the current chain.")
        else:
            self._display_report(report)
        if report is None or not report.ok:
            self._history_records = LinkedSequence()
            self.history_content.grid_remove()
            self.history_gate.grid()
            self.gate_message.configure(text=report.message if report is not None else "Run the integrity check in Approval to open record history.")
            self._filter_history()
        else:
            self.history_gate.grid_remove()
            self.history_content.grid()
            self._history_records = report.records
            self._filter_history()
        self._update_controls()

    def _update_controls(self):
        for control in self._controls:
            control.configure(state="disabled" if self.busy else "normal")
        if hasattr(self, "process_button") and not self.busy:
            self.process_button.configure(state="normal" if self.service.pending_count else "disabled")
        if hasattr(self, "archive_button") and not self.busy:
            approved = self.service.report is not None and self.service.report.ok
            self.archive_button.configure(state="normal" if approved else "disabled")
            self.open_archive_button.configure(state="normal" if self.last_archive else "disabled")

    def _display_report(self, report: VerificationReport):
        self.approval_title.configure(text="Integrity verified" if report.ok else "Integrity check failed", fg=TEAL if report.ok else RED)
        tail_note = " Newest seal content was ignored as required." if report.ignored_tail_content else ""
        self.approval_message.configure(text=report.message + f" Checked: {report.checked_at.replace('T', ' ')}." + tail_note)
        self._steps = report.steps
        selection = self.check_tree.selection()
        for item in self.check_tree.get_children():
            self.check_tree.delete(item)
        for step in report.steps:
            self.check_tree.insert("", "end", iid=str(step.index), values=(f"#{step.index}", step.kind.title(), "Match" if step.ok else "MISMATCH"))
        children = self.check_tree.get_children()
        if children:
            chosen = str(report.failure_node) if report.failure_node and str(report.failure_node) in children else (selection[0] if selection and selection[0] in children else children[0])
            self.check_tree.selection_set(chosen)
            self._select_step()

    def _select_step(self, _event=None):
        selection = self.check_tree.selection()
        if not selection:
            return
        for step in self._steps:
            if str(step.index) == selection[0]:
                self.step_description.configure(text=("Genesis uses the zero-hash sentinel." if step.index == 1 else f"Node #{step.index} stores the digest of node #{step.index - 1}."))
                self.stored_hash.configure(text=step.stored)
                self.calculated_hash.configure(text=step.calculated, fg=INK if step.ok else RED)
                return

    def _select_pending(self, _event=None):
        selection = self.queue_tree.selection()
        if not selection:
            return
        for record in self.service.pending():
            if str(record.request_id) == selection[0]:
                self.pending_title.configure(text=record.title)
                self.pending_meta.configure(text=f"{record.reference} · {record.patient} · {record.author} · Visit: {record.visit_date}")
                self.pending_notes.configure(text=record.notes[:500] + ("…" if len(record.notes) > 500 else ""))
                return

    def _tab_changed(self, _event=None):
        if self.busy:
            return
        if self.tabs.select() == str(self.history_page) and self.service.report is not None and self.service.report.ok:
            self._run_job(self.service.history, self._history_ready, "Checking records before opening history…")

    def _history_ready(self, records):
        self._history_records = records
        self._filter_history()
        self._set_status(f"{len(records)} verified record(s). History is newest first.")

    def _filter_history(self, *_args):
        if not hasattr(self, "history_tree"):
            return
        search = self.history_search.get().strip().casefold()
        selection = self.history_tree.selection()
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        count = 0
        for record in self._history_records:
            haystack = f"{record.reference} {record.request_id} {record.patient} {record.title}".casefold()
            if search and search not in haystack:
                continue
            count += 1
            self.history_tree.insert("", "end", iid=str(record.request_id), values=(record.reference, record.patient, record.title,
                                     record.recorded_at[:16].replace("T", " ")))
        self.history_count.configure(text=f"{count} verified record(s)" if count else ("No matching records" if search else "No records yet. Process a queued request to create the first pair."))
        children = self.history_tree.get_children()
        if children:
            self.history_tree.selection_set(selection[0] if selection and selection[0] in children else children[0])
            self._select_history()
        else:
            self.history_title.configure(text="Select a verified record")
            self.history_meta.configure(text="")
            self._show_notes("")

    def _show_notes(self, value):
        self.history_notes.configure(state="normal")
        self.history_notes.delete("1.0", "end")
        self.history_notes.insert("1.0", value)
        self.history_notes.configure(state="disabled")

    def _select_history(self, _event=None):
        selection = self.history_tree.selection()
        if not selection:
            return
        for record in self._history_records:
            if str(record.request_id) == selection[0]:
                self.history_title.configure(text=record.title)
                self.history_meta.configure(text=f"{record.reference} · {record.patient} · {record.author} · Visit: {record.visit_date}\nSubmitted: {record.submitted_at}    Processed: {record.recorded_at}")
                self._show_notes(record.notes)
                return

    def _wheel(self, event, direction=None):
        if isinstance(event.widget, (tk.Text, ttk.Treeview)):
            return
        page = self.root.nametowidget(self.tabs.select())
        if isinstance(page, ScrollPage):
            amount = direction if direction is not None else (-1 if event.delta > 0 else 1)
            page.canvas.yview_scroll(amount * 3, "units")

    def close(self):
        if self.closed:
            return
        if self.busy:
            self._closing = True
            self._set_status("Finishing the current save before closing…")
        else:
            self._shutdown()

    def _shutdown(self):
        self.service.close()
        self.closed = True
        self.root.destroy()
