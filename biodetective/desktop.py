"""Minimal ChatGPT-inspired BioDetective desktop interface."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

from . import APP_NAME, APP_VERSION
from .hardware import detect_hardware
from .ollama_client import OllamaClient, OllamaError
from .pipeline import follow_up_answer, run_investigation
from .storage import InvestigationStore, report_markdown


BG = "#f7f8fa"
PANEL = "#ffffff"
SIDEBAR = "#f0f2f5"
INK = "#20242d"
MUTED = "#667085"
LINE = "#e4e7ec"
BLUE = "#3157d5"
BLUE_LIGHT = "#edf2ff"
GREEN = "#17845d"
GREEN_LIGHT = "#eaf7f1"
AMBER = "#a45b12"
AMBER_LIGHT = "#fff4e5"
RED = "#ad3d3d"
RED_LIGHT = "#fff0ef"


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=BG, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, background=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._resize_scroll)
        self.canvas.bind("<Configure>", self._resize_inner)
        self.canvas.bind_all("<MouseWheel>", self._mousewheel, add="+")

    def _resize_scroll(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_inner(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _mousewheel(self, event: tk.Event) -> None:
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class BioDetectiveApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} · Evidence-grounded biology")
        self.root.geometry("1280x840")
        self.root.minsize(980, 680)
        self.root.configure(background=BG)
        self._fonts: dict[tuple[str, int, str, bool], tkfont.Font] = {}
        self.root.option_add("*Font", self._font(10))

        self.client = OllamaClient()
        self.store = InvestigationStore()
        self.hardware = detect_hardware()
        self.local_models: list[dict[str, Any]] = []
        self.active_investigation: dict[str, Any] | None = None
        self.active_id: str | None = None
        self.chat_history: list[dict[str, str]] = []
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.model_var = tk.StringVar(value="")
        self.connection_var = tk.StringVar(value="Checking local model runtime…")
        self.connection_color = MUTED

        self._configure_styles()
        self._build_shell()
        self._render_home()
        self._refresh_models()
        self._poll_events()

    def _font(
        self,
        size: int,
        weight: str = "normal",
        *,
        family: str = "Segoe UI",
        underline: bool = False,
    ) -> tkfont.Font:
        key = (family, size, weight, underline)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(
                root=self.root,
                family=family,
                size=size,
                weight=weight,
                underline=underline,
            )
        return self._fonts[key]

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Sidebar.TFrame", background=SIDEBAR)
        style.configure("Sidebar.TLabel", background=SIDEBAR, foreground=INK)
        style.configure("SidebarMuted.TLabel", background=SIDEBAR, foreground=MUTED)
        style.configure("TCombobox", padding=(8, 7), fieldbackground=PANEL)
        style.configure("Horizontal.TProgressbar", troughcolor=LINE, background=BLUE, bordercolor=LINE, lightcolor=BLUE, darkcolor=BLUE)

    def _build_shell(self) -> None:
        shell = tk.Frame(self.root, background=BG)
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, width=264, background=SIDEBAR, padx=18, pady=18)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self._build_sidebar()

        main = tk.Frame(shell, background=BG)
        main.pack(side="left", fill="both", expand=True)
        self._build_topbar(main)

        self.page = ScrollableFrame(main)
        self.page.pack(fill="both", expand=True, padx=(14, 14), pady=(4, 12))
        self.page.inner.grid_columnconfigure(0, weight=1)

    def _build_sidebar(self) -> None:
        brand = tk.Frame(self.sidebar, background=SIDEBAR)
        brand.pack(fill="x", pady=(2, 22))
        mark = tk.Label(brand, text="◉", font=self._font(23, family="Segoe UI Symbol"), fg=BLUE, bg=SIDEBAR)
        mark.pack(side="left", padx=(0, 9))
        labels = tk.Frame(brand, background=SIDEBAR)
        labels.pack(side="left")
        tk.Label(labels, text="BioDetective", font=self._font(16, "bold"), fg=INK, bg=SIDEBAR).pack(anchor="w")
        tk.Label(labels, text="LOCAL RESEARCH WORKSPACE", font=self._font(7, "bold"), fg=MUTED, bg=SIDEBAR).pack(anchor="w", pady=(1, 0))

        self._button(self.sidebar, "＋   New investigation", self.new_investigation, primary=True).pack(fill="x", pady=(0, 18), ipady=5)
        self._sidebar_label("LOCAL MODEL")
        self.model_combo = ttk.Combobox(self.sidebar, textvariable=self.model_var, state="readonly", values=[])
        self.model_combo.pack(fill="x", pady=(6, 7))
        self._button(self.sidebar, "Download recommended model", self._pull_recommended).pack(fill="x", pady=(0, 6))
        self._button(self.sidebar, "Refresh model list", self._refresh_models).pack(fill="x", pady=(0, 10))
        self.connection_label = tk.Label(self.sidebar, textvariable=self.connection_var, justify="left", wraplength=218, anchor="w", bg=SIDEBAR, fg=self.connection_color, font=self._font(9))
        self.connection_label.pack(fill="x", pady=(0, 16))

        self._sidebar_label("RECENT INVESTIGATIONS")
        self.history_frame = tk.Frame(self.sidebar, background=SIDEBAR)
        self.history_frame.pack(fill="both", expand=True, pady=(7, 8))
        self._render_history()

        bottom = tk.Frame(self.sidebar, background=SIDEBAR)
        bottom.pack(fill="x", side="bottom", pady=(10, 0))
        tk.Frame(bottom, height=1, background=LINE).pack(fill="x", pady=(0, 10))
        self.hardware_label = tk.Label(
            bottom,
            text=self._hardware_summary(),
            bg=SIDEBAR,
            fg=MUTED,
            justify="left",
            wraplength=220,
            font=self._font(8),
        )
        self.hardware_label.pack(anchor="w")
        self._button(bottom, "ⓘ   About & privacy", self._show_about, flat=True).pack(fill="x", pady=(10, 0))

    def _build_topbar(self, parent: tk.Misc) -> None:
        bar = tk.Frame(parent, bg=BG, padx=26, pady=15)
        bar.pack(fill="x")
        self.top_title = tk.Label(bar, text="New investigation", font=self._font(13, "bold"), bg=BG, fg=INK)
        self.top_title.pack(side="left")
        self.local_badge = tk.Label(bar, text="●  ON-DEVICE AI", font=self._font(8, "bold"), bg=GREEN_LIGHT, fg=GREEN, padx=10, pady=6)
        self.local_badge.pack(side="right")
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", padx=24)

    def _hardware_summary(self) -> str:
        ram = self.hardware.get("total_ram_gib", 0)
        threads = self.hardware.get("cpu_threads", 0)
        gpu = self.hardware.get("gpu", "GPU details unavailable")
        recommendation = self.hardware.get("recommended_model", "qwen3:1.7b")
        ram_text = f"{ram:g} GB RAM" if ram else "RAM detection unavailable"
        return f"DEVICE PROFILE\n{ram_text} · {threads} CPU threads\n{str(gpu)[:62]}\nSuggested: {recommendation}"

    def _sidebar_label(self, text: str) -> None:
        tk.Label(self.sidebar, text=text, bg=SIDEBAR, fg=MUTED, font=self._font(8, "bold")).pack(anchor="w")

    def _button(self, parent: tk.Misc, text: str, command: Any, *, primary: bool = False, flat: bool = False) -> tk.Button:
        bg = BLUE if primary else SIDEBAR if flat else PANEL
        fg = "#ffffff" if primary else MUTED if flat else INK
        active_bg = "#2548bb" if primary else "#e7eaf0" if flat else "#f7f8fa"
        return tk.Button(
            parent,
            text=text,
            command=command,
            anchor="w",
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            cursor="hand2",
            font=self._font(9, "bold" if primary else "normal"),
        )

    def _render_history(self) -> None:
        for child in self.history_frame.winfo_children():
            child.destroy()
        items = self.store.list_recent()
        if not items:
            tk.Label(self.history_frame, text="Your saved investigations\nwill appear here.", bg=SIDEBAR, fg=MUTED, justify="left", font=self._font(9)).pack(anchor="w", pady=4)
            return
        for item in items:
            title = item["title"] or "Untitled investigation"
            button = tk.Button(
                self.history_frame,
                text="  " + title[:31] + ("…" if len(title) > 31 else ""),
                command=lambda record_id=item["id"]: self._load_investigation(record_id),
                anchor="w",
                relief="flat",
                bd=0,
                padx=4,
                pady=7,
                bg=SIDEBAR,
                fg=INK,
                activebackground="#e7eaf0",
                activeforeground=INK,
                cursor="hand2",
                font=self._font(9),
            )
            button.pack(fill="x", pady=1)

    def _new_card(self, parent: tk.Misc, *, padding: int = 20) -> tk.Frame:
        outer = tk.Frame(parent, bg=PANEL, highlightbackground=LINE, highlightthickness=1, padx=padding, pady=padding)
        return outer

    def _section_title(self, parent: tk.Misc, title: str, subtitle: str | None = None) -> None:
        tk.Label(parent, text=title, font=self._font(12, "bold"), bg=PANEL, fg=INK).pack(anchor="w")
        if subtitle:
            tk.Label(parent, text=subtitle, font=self._font(9), bg=PANEL, fg=MUTED, wraplength=760, justify="left").pack(anchor="w", pady=(4, 0))

    def _clear_page(self) -> None:
        for child in self.page.inner.winfo_children():
            child.destroy()
        self.page.canvas.yview_moveto(0)

    def _render_home(self, claim: str = "") -> None:
        self._clear_page()
        self.active_investigation = None
        self.active_id = None
        self.chat_history = []
        self.top_title.configure(text="New investigation")

        hero = tk.Frame(self.page.inner, bg=BG, padx=28, pady=36)
        hero.grid(row=0, column=0, sticky="ew")
        tk.Label(hero, text="Evidence first.\nReasoning you can inspect.", font=self._font(28, "bold"), bg=BG, fg=INK, justify="left").pack(anchor="w")
        tk.Label(
            hero,
            text="Investigate a biological claim with a local AI model, traceable literature, competing hypotheses, and visible uncertainty.",
            font=self._font(11),
            bg=BG,
            fg=MUTED,
            wraplength=780,
            justify="left",
        ).pack(anchor="w", pady=(12, 0))

        card = self._new_card(self.page.inner, padding=20)
        card.grid(row=1, column=0, sticky="ew", padx=24)
        tk.Label(card, text="BIOLOGICAL CLAIM", font=self._font(8, "bold"), fg=MUTED, bg=PANEL).pack(anchor="w")
        self.claim_entry = tk.Text(card, height=4, wrap="word", font=self._font(12), bg=PANEL, fg=INK, bd=0, padx=0, pady=10, insertbackground=BLUE, undo=True)
        self.claim_entry.pack(fill="x")
        self.claim_entry.insert("1.0", claim)
        self.claim_entry.configure(highlightthickness=0)
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text="Example: Does TP53 loss increase drug resistance in breast cancer cells?", font=self._font(9), bg=PANEL, fg=MUTED).pack(side="left")
        self.run_button = self._button(row, "Investigate claim  →", self._start_investigation, primary=True)
        self.run_button.pack(side="right")

        self.progress_frame = self._new_card(self.page.inner, padding=16)
        self.progress_frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(12, 0))
        self.progress_label = tk.Label(self.progress_frame, text="", bg=PANEL, fg=MUTED, anchor="w", font=self._font(9))
        self.progress_label.pack(fill="x")
        self.progress_bar = ttk.Progressbar(self.progress_frame, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", pady=(10, 0))
        self.progress_frame.grid_remove()

        note = tk.Frame(self.page.inner, bg=BG, padx=27, pady=22)
        note.grid(row=3, column=0, sticky="ew")
        tk.Label(note, text="LOCAL MODEL", font=self._font(8, "bold"), bg=BG, fg=GREEN).pack(anchor="w")
        tk.Label(note, text="Model inference stays on this computer. Literature search uses Europe PMC; source metadata and abstracts are passed to the local model. No OpenAI or cloud-model API is used.", font=self._font(9), bg=BG, fg=MUTED, wraplength=820, justify="left").pack(anchor="w", pady=(5, 0))

    def _set_connection(self, text: str, color: str) -> None:
        self.connection_var.set(text)
        self.connection_label.configure(fg=color)

    def _refresh_models(self) -> None:
        def worker() -> None:
            try:
                available = self.client.is_available()
                models = self.client.list_models() if available else []
                self.events.put(("models", (available, models)))
            except OllamaError:
                self.events.put(("models", (False, [])))

        threading.Thread(target=worker, daemon=True).start()

    def _update_model_list(self, available: bool, models: list[dict[str, Any]]) -> None:
        self.local_models = models
        names = [str(item.get("name", "")) for item in models if item.get("name")]
        self.model_combo.configure(values=names)
        if self.model_var.get() not in names:
            preferred = str(self.hardware.get("recommended_model", ""))
            self.model_var.set(preferred if preferred in names else (names[0] if names else ""))
        if available:
            version = self.client.version()
            self._set_connection(f"● Ollama ready{f' · v{version}' if version else ''}\nInference runs locally.", GREEN)
        else:
            self._set_connection("○ Ollama is not running. Install/start the local runtime to use BioDetective.", AMBER)
        self.local_badge.configure(text="●  ON-DEVICE AI" if available else "○  LOCAL MODEL NEEDED", bg=GREEN_LIGHT if available else AMBER_LIGHT, fg=GREEN if available else AMBER)

    def _pull_recommended(self) -> None:
        model = str(self.hardware.get("recommended_model", "qwen3:1.7b"))
        if not self.client.is_available():
            if messagebox.askyesno("Ollama is required", "BioDetective uses Ollama to run models privately on this computer. Open the official Windows download page?"):
                webbrowser.open("https://ollama.com/download/windows")
            return
        if self.busy:
            return
        self.busy = True
        self._set_connection(f"Downloading {model}…\nThis can take several minutes.", BLUE)
        self.model_combo.configure(state="disabled")

        def worker() -> None:
            try:
                self.client.pull_model(model, lambda status, percent: self.events.put(("pull_progress", (status, percent))))
                self.events.put(("pull_done", model))
            except Exception as exc:
                self.events.put(("pull_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _start_investigation(self) -> None:
        if self.busy:
            return
        claim = self.claim_entry.get("1.0", "end").strip()
        if not claim:
            messagebox.showinfo("Add a claim", "Enter one biological claim to begin the investigation.")
            self.claim_entry.focus_set()
            return
        model = self.model_var.get().strip()
        if not model:
            messagebox.showinfo("Choose a local model", "Download the recommended model, or select an installed model in the sidebar.")
            return
        self.busy = True
        self.run_button.configure(state="disabled", text="Investigating…")
        self.progress_frame.grid()
        self.progress_label.configure(text="Starting local investigation…")
        self.progress_bar.start(12)
        self.page.canvas.yview_moveto(0)

        def progress(stage: str, detail: str) -> None:
            self.events.put(("progress", (stage, detail)))

        def worker() -> None:
            try:
                data = run_investigation(claim, model, self.client, progress)
                self.events.put(("investigation_done", data))
            except Exception as exc:
                self.events.put(("investigation_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "models":
                    self._update_model_list(*payload)
                elif kind == "progress":
                    stage, detail = payload
                    self.progress_label.configure(text=f"{stage}  ·  {detail}")
                elif kind == "pull_progress":
                    status, percent = payload
                    suffix = f" {percent}%" if percent is not None else ""
                    self._set_connection(f"{status}{suffix}\nDownloading into Ollama's local model store.", BLUE)
                elif kind == "pull_done":
                    self.busy = False
                    self.model_combo.configure(state="readonly")
                    self._refresh_models()
                    self._set_connection(f"{payload} is ready. Model files stay on this computer.", GREEN)
                elif kind == "pull_error":
                    self.busy = False
                    self.model_combo.configure(state="readonly")
                    self._set_connection("Model download failed. Check Ollama and your connection.", RED)
                    messagebox.showerror("Could not download model", str(payload))
                elif kind == "investigation_done":
                    self.busy = False
                    self.progress_bar.stop()
                    self.progress_frame.grid_remove()
                    self.run_button.configure(state="normal", text="Investigate claim  →")
                    self.active_investigation = payload
                    self.active_id = self.store.save(payload)
                    self.chat_history = []
                    self.top_title.configure(text="Investigation report")
                    self._render_results(payload)
                    self._render_history()
                    self._set_connection("● Local model ready\nInvestigation saved on this computer.", GREEN)
                elif kind == "investigation_error":
                    self.busy = False
                    self.progress_bar.stop()
                    self.progress_frame.grid_remove()
                    self.run_button.configure(state="normal", text="Investigate claim  →")
                    self._set_connection("Investigation stopped. No report was saved.", RED)
                    messagebox.showerror("Investigation could not finish", str(payload))
                elif kind == "answer_done":
                    self.busy = False
                    question, answer = payload
                    self._append_chat_message("assistant", answer)
                    self._set_chat_busy(False)
                elif kind == "answer_error":
                    self.busy = False
                    self._append_chat_message("assistant", f"I couldn't complete that local follow-up: {payload}")
                    self._set_chat_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _render_results(self, data: dict[str, Any]) -> None:
        self._clear_page()
        self.active_investigation = data
        claim_head = tk.Frame(self.page.inner, bg=BG, padx=24, pady=20)
        claim_head.grid(row=0, column=0, sticky="ew")
        tk.Label(claim_head, text="BIOLOGICAL CLAIM", font=self._font(8, "bold"), bg=BG, fg=MUTED).pack(anchor="w")
        tk.Label(claim_head, text=data.get("claim", ""), font=self._font(17, "bold"), bg=BG, fg=INK, wraplength=880, justify="left").pack(anchor="w", pady=(6, 0))
        toolbar = tk.Frame(claim_head, bg=BG)
        toolbar.pack(anchor="w", pady=(11, 0))
        self._pill(toolbar, f"LOCAL MODEL · {data.get('model', '')}", GREEN_LIGHT, GREEN).pack(side="left", padx=(0, 7))
        self._pill(toolbar, f"{len(data.get('articles', []))} SOURCE CANDIDATES", BLUE_LIGHT, BLUE).pack(side="left", padx=(0, 7))
        self._button(toolbar, "Export report", self._export_report).pack(side="left")

        summary = self._new_card(self.page.inner, padding=18)
        summary.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 12))
        self._section_title(summary, "Overall assessment", "Automated results are provisional. Open each source and verify its methods and findings.")
        tk.Label(summary, text=data.get("assessment", ""), font=self._font(10), bg=PANEL, fg=INK, wraplength=810, justify="left").pack(anchor="w", pady=(12, 8))
        self._build_scorebar(summary, data.get("bes", {}))

        hypotheses = data.get("analysis", {}).get("hypotheses", [])
        hcard = self._new_card(self.page.inner, padding=18)
        hcard.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 12))
        self._section_title(hcard, "Competing hypotheses", "Candidate explanations to compare; the model's hypotheses are not established mechanisms.")
        if hypotheses:
            for index, hypothesis in enumerate(hypotheses[:5]):
                row = tk.Frame(hcard, bg=PANEL)
                row.pack(fill="x", anchor="w", pady=(12 if index == 0 else 8, 0))
                tk.Label(row, text=str(hypothesis.get("id", f"H{index+1}")), bg=BLUE_LIGHT, fg=BLUE, padx=8, pady=5, font=self._font(8, "bold")).pack(side="left", anchor="n", padx=(0, 10))
                body = tk.Frame(row, bg=PANEL)
                body.pack(side="left", fill="x", expand=True)
                tk.Label(body, text=str(hypothesis.get("label", "Candidate explanation")), bg=PANEL, fg=INK, font=self._font(10, "bold")).pack(anchor="w")
                tk.Label(body, text=str(hypothesis.get("description", "")), bg=PANEL, fg=MUTED, font=self._font(9), wraplength=750, justify="left").pack(anchor="w", pady=(3, 0))
                if hypothesis.get("discriminating_test"):
                    tk.Label(body, text="Distinguishing observation: " + str(hypothesis["discriminating_test"]), bg=PANEL, fg=BLUE, font=self._font(9), wraplength=750, justify="left").pack(anchor="w", pady=(4, 0))
        else:
            tk.Label(hcard, text="The local model did not return structured hypotheses. Inspect the query and try again with a more specific claim.", bg=PANEL, fg=MUTED, font=self._font(9), wraplength=760, justify="left").pack(anchor="w", pady=(12, 0))

        graph = self._new_card(self.page.inner, padding=18)
        graph.grid(row=3, column=0, sticky="ew", padx=24, pady=(0, 12))
        self._section_title(graph, "Evidence graph", "Graph edges are proposed relationships; colored evidence attaches to the relationship being assessed.")
        self._draw_graph(graph, data.get("relationship_assessments", data.get("analysis", {}).get("relationships", [])), data.get("evidence", []))

        evidence_card = self._new_card(self.page.inner, padding=18)
        evidence_card.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 12))
        evidence_rows = data.get("articles", [])
        self._section_title(evidence_card, "Evidence cards", f"{len(evidence_rows)} retrieved records · classifications are model-proposed · only titles/abstracts were used unless stated otherwise.")
        if evidence_rows:
            for i, article in enumerate(evidence_rows):
                self._evidence_card(evidence_card, i + 1, article)
        else:
            tk.Label(evidence_card, text="No source candidates were found. Search coverage may be incomplete; this is not evidence against the claim.", bg=PANEL, fg=MUTED, font=self._font(9), wraplength=760, justify="left").pack(anchor="w", pady=(12, 0))

        gaps = self._new_card(self.page.inner, padding=18)
        gaps.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 12))
        self._section_title(gaps, "What’s missing?", "The automated gap note is a prompt for review, not an experimental protocol.")
        self._render_gap(gaps, data)

        chat = self._new_card(self.page.inner, padding=18)
        chat.grid(row=6, column=0, sticky="ew", padx=24, pady=(0, 30))
        self._section_title(chat, "Ask about this evidence", "Follow-up answers use the current investigation and local model only.")
        self.chat_messages = tk.Frame(chat, bg=PANEL)
        self.chat_messages.pack(fill="x", pady=(8, 0))
        self.chat_input_row = tk.Frame(chat, bg=PANEL)
        self.chat_input_row.pack(fill="x", pady=(10, 0))
        self.chat_entry = tk.Entry(self.chat_input_row, font=self._font(10), bd=0, relief="flat", bg="#f7f8fa", fg=INK, insertbackground=BLUE)
        self.chat_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self.chat_entry.bind("<Return>", lambda _event: self._send_follow_up())
        self.chat_button = self._button(self.chat_input_row, "Ask  →", self._send_follow_up, primary=True)
        self.chat_button.pack(side="right")
        self.page.canvas.yview_moveto(0)

    def _pill(self, parent: tk.Misc, text: str, bg: str, fg: str) -> tk.Label:
        return tk.Label(parent, text=text, font=self._font(8, "bold"), bg=bg, fg=fg, padx=9, pady=5)

    def _build_scorebar(self, parent: tk.Misc, bes: dict[str, Any]) -> None:
        score = bes.get("score")
        counts = tk.Frame(parent, bg=PANEL)
        counts.pack(fill="x", pady=(7, 10))
        self._count_chip(counts, "Supporting", bes.get("supporting", 0), GREEN, GREEN_LIGHT).pack(side="left", padx=(0, 8))
        self._count_chip(counts, "Contradicting", bes.get("contradicting", 0), RED, RED_LIGHT).pack(side="left", padx=(0, 8))
        self._count_chip(counts, "Insufficient", bes.get("insufficient", 0), AMBER, AMBER_LIGHT).pack(side="left")
        if score is None:
            score_text = "Not enough classified evidence to calculate"
            pct = 0
        else:
            score_text = f"Pilot BES · {score}/100 weighted support share"
            pct = score
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(2, 5))
        tk.Label(top, text=score_text, font=self._font(10, "bold"), bg=PANEL, fg=INK).pack(side="left")
        tk.Label(top, text="UNCALIBRATED", font=self._font(8, "bold"), bg=AMBER_LIGHT, fg=AMBER, padx=8, pady=4).pack(side="right")
        track = tk.Frame(parent, bg=LINE, height=7)
        track.pack(fill="x")
        track.pack_propagate(False)
        if pct > 0:
            fill = tk.Frame(track, bg=GREEN if pct >= 60 else AMBER if pct >= 40 else RED, width=1)
            fill.place(relx=0, rely=0, relwidth=pct / 100, relheight=1)
        tk.Label(parent, text=bes.get("label", ""), font=self._font(8), bg=PANEL, fg=MUTED, wraplength=770, justify="left").pack(anchor="w", pady=(6, 0))
        tk.Label(parent, text="Formula: Σ(support design×directness weights) ÷ Σ(all classified design×directness weights). It summarizes the retrieved classified sample, not truth or total evidence strength.", font=self._font(8), bg=PANEL, fg=MUTED, wraplength=780, justify="left").pack(anchor="w", pady=(4, 0))

    def _count_chip(self, parent: tk.Misc, label: str, count: int, fg: str, bg: str) -> tk.Frame:
        chip = tk.Frame(parent, bg=bg, padx=9, pady=6)
        tk.Label(chip, text=f"{label}  {count}", bg=bg, fg=fg, font=self._font(9, "bold")).pack()
        return chip

    def _draw_graph(self, parent: tk.Misc, relationships: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> None:
        rows = relationships[:6]
        canvas_height = max(96, 42 * len(rows) + 18)
        canvas = tk.Canvas(parent, height=canvas_height, bg="#fbfcfe", highlightthickness=1, highlightbackground=LINE)
        canvas.pack(fill="x", pady=(12, 0))
        if not rows:
            canvas.create_text(24, 34, anchor="nw", text="No structured relationships returned. The claim and source records remain available below.", fill=MUTED, font=self._font(9))
            return
        def draw_rows(_event: tk.Event | None = None) -> None:
            canvas.delete("all")
            width = max(canvas.winfo_width(), 640)
            for index, edge in enumerate(rows):
                y = 24 + index * 42
                edge_id = str(edge.get("id", f"R{index + 1}"))
                linked = [item for item in evidence if edge_id in item.get("relationship_ids", [])]
                support = sum(1 for item in linked if item.get("polarity") == "supporting")
                contradict = sum(1 for item in linked if item.get("polarity") == "contradicting")
                insufficient = sum(1 for item in linked if item.get("polarity") == "insufficient")
                source = str(edge.get("source", "Unresolved"))
                target = str(edge.get("target", "Unresolved"))
                x0, x1 = 105, max(350, width - 270)
                node_w = min(126, max(78, width * 0.14))
                canvas.create_rectangle(10, y - 14, 48, y + 14, fill=BLUE_LIGHT, outline="")
                canvas.create_text(29, y, text=edge_id, fill=BLUE, font=self._font(8, "bold"))
                canvas.create_rectangle(x0, y - 14, x0 + node_w, y + 14, fill="#f3f5fa", outline=LINE)
                canvas.create_text(x0 + node_w / 2, y, text=source[:18] + ("…" if len(source) > 18 else ""), fill=INK, font=self._font(8, "bold"))
                line_color = GREEN if support and not contradict else RED if contradict and not support else AMBER if support or contradict else "#98a2b3"
                canvas.create_line(x0 + node_w + 4, y, x1 - 4, y, fill=line_color, width=2, arrow=tk.LAST, arrowshape=(8, 10, 4))
                canvas.create_text((x0 + node_w + x1) / 2, y - 11, text=str(edge.get("relation", "proposed link"))[:24], fill=MUTED, font=self._font(7))
                canvas.create_rectangle(x1, y - 14, x1 + node_w, y + 14, fill="#f3f5fa", outline=LINE)
                canvas.create_text(x1 + node_w / 2, y, text=target[:18] + ("…" if len(target) > 18 else ""), fill=INK, font=self._font(8, "bold"))
                score = edge.get("pilot_bes")
                score_text = f"BES {score}" if score is not None else "BES —"
                canvas.create_text(x1 + node_w + 12, y, anchor="w", text=f"+ {support}  ·  − {contradict}  ·  ? {insufficient}  ·  {score_text}", fill=MUTED, font=self._font(8))
        canvas.bind("<Configure>", draw_rows)
        canvas.after_idle(draw_rows)

    def _evidence_card(self, parent: tk.Misc, index: int, article: dict[str, Any]) -> None:
        item = article.get("evidence", {})
        polarity = str(item.get("polarity", "insufficient"))
        if polarity == "supporting":
            bg, fg = GREEN_LIGHT, GREEN
        elif polarity == "contradicting":
            bg, fg = RED_LIGHT, RED
        else:
            bg, fg = AMBER_LIGHT, AMBER
        card = tk.Frame(parent, bg="#fbfcfe", highlightbackground=LINE, highlightthickness=1, padx=13, pady=11)
        card.pack(fill="x", pady=(12, 0))
        head = tk.Frame(card, bg="#fbfcfe")
        head.pack(fill="x")
        tk.Label(head, text=f"{index:02d}", bg=BLUE_LIGHT, fg=BLUE, padx=7, pady=4, font=self._font(8, "bold")).pack(side="left", padx=(0, 8))
        title = str(article.get("title", "Untitled record"))
        tk.Label(head, text=title, bg="#fbfcfe", fg=INK, font=self._font(9, "bold"), wraplength=660, justify="left").pack(side="left", fill="x", expand=True, anchor="w")
        tk.Label(head, text=polarity.upper(), bg=bg, fg=fg, padx=7, pady=4, font=self._font(7, "bold")).pack(side="right", padx=(6, 0))
        meta = f"{article.get('authors', '')[:90]} · {article.get('year', 'year n/a')} · {article.get('journal', 'journal n/a')}"
        tk.Label(card, text=meta, bg="#fbfcfe", fg=MUTED, font=self._font(8), wraplength=760, justify="left").pack(anchor="w", pady=(7, 0))
        doi = article.get("doi") or (f"PMID {article['pmid']}" if article.get("pmid") else "Europe PMC record")
        link = tk.Label(card, text=f"{doi}  ↗", bg="#fbfcfe", fg=BLUE, cursor="hand2", font=self._font(8, underline=True))
        link.pack(anchor="w", pady=(2, 0))
        link.bind("<Button-1>", lambda _event, url=article.get("url", ""): webbrowser.open(url))
        summary = str(item.get("finding_summary", "No finding was extracted."))
        tk.Label(card, text=summary, bg="#fbfcfe", fg=INK, font=self._font(9), wraplength=770, justify="left").pack(anchor="w", pady=(7, 0))
        detail = f"{item.get('study_design', 'unknown')} · {item.get('directness', 'unclear')} · model: {item.get('biological_model', 'unknown')} · locator: {item.get('source_locator', 'metadata only')} · {item.get('review_state', 'unreviewed')}"
        tk.Label(card, text=detail, bg="#fbfcfe", fg=MUTED, font=self._font(8), wraplength=770, justify="left").pack(anchor="w", pady=(6, 0))
        limitations = item.get("limitations", [])
        if limitations:
            tk.Label(card, text="Limitations: " + "; ".join(str(x) for x in limitations), bg="#fbfcfe", fg=MUTED, font=self._font(8), wraplength=770, justify="left").pack(anchor="w", pady=(4, 0))
        relation_ids = item.get("relationship_ids", [])
        if relation_ids:
            tk.Label(card, text="Mapped proposition(s): " + ", ".join(relation_ids), bg="#fbfcfe", fg=BLUE, font=self._font(8)).pack(anchor="w", pady=(4, 0))

    def _render_gap(self, parent: tk.Misc, data: dict[str, Any]) -> None:
        evidence = data.get("evidence", [])
        relationships = data.get("relationship_assessments", [])
        direct = sum(1 for row in evidence if row.get("directness") == "direct")
        unknown = sum(1 for row in evidence if row.get("polarity") == "insufficient")
        if not evidence:
            gap = "No source evidence was assessed. The immediate gap is retrieving relevant studies; an empty search is not evidence that the relationship is absent."
        elif unknown or not direct:
            gap = f"Direct causal evidence is limited in the retrieved sample: {direct} record(s) were classified as direct, and {unknown} were insufficient from the available text. Review full texts and test the weakest claimed relationship in its biological context."
        else:
            gap = "The retrieved sample contains direct evidence candidates. Check independent replication, methodological agreement, and whether the evidence covers every edge in the proposed mechanism."
        tk.Label(parent, text=gap, bg=PANEL, fg=INK, font=self._font(9), wraplength=790, justify="left").pack(anchor="w", pady=(11, 0))
        linked = [row for row in relationships if row.get("linked_records", 0) > 0]
        if linked:
            strongest = max(linked, key=lambda row: (row.get("support_weight", 0), row.get("supporting", 0)))
            weakest = min(relationships, key=lambda row: (row.get("linked_records", 0), row.get("supporting", 0)))
            strongest_text = f"Most supporting records: {strongest.get('source', '')} → {strongest.get('target', '')} ({strongest.get('supporting', 0)} support, {strongest.get('contradicting', 0)} conflict)."
            weakest_text = f"Least covered proposed link: {weakest.get('source', '')} → {weakest.get('target', '')} ({weakest.get('linked_records', 0)} mapped records)."
            tk.Label(parent, text=strongest_text + "\n" + weakest_text, bg="#f7f8fa", fg=MUTED, font=self._font(8), wraplength=780, justify="left", padx=10, pady=8).pack(anchor="w", fill="x", pady=(10, 0))
        elif relationships:
            tk.Label(parent, text="No retrieved evidence was confidently mapped to a specific graph edge. The source cards remain available for manual review.", bg=AMBER_LIGHT, fg=AMBER, font=self._font(8), wraplength=780, justify="left", padx=10, pady=8).pack(anchor="w", fill="x", pady=(10, 0))
        tk.Label(parent, text="Possible next step: inspect full-text methods and prioritize a perturbation or replication that distinguishes the leading hypotheses. Have a domain expert review the design.", bg=BLUE_LIGHT, fg=BLUE, font=self._font(9), wraplength=780, justify="left", padx=11, pady=9).pack(anchor="w", pady=(10, 0))

    def _send_follow_up(self) -> None:
        if self.busy or not self.active_investigation or not hasattr(self, "chat_entry"):
            return
        question = self.chat_entry.get().strip()
        model = self.model_var.get().strip()
        if not question:
            return
        if not model:
            messagebox.showinfo("Choose a local model", "Select an installed model in the sidebar.")
            return
        self.chat_entry.delete(0, "end")
        self._append_chat_message("user", question)
        self.busy = True
        self._set_chat_busy(True)

        def worker() -> None:
            try:
                answer = follow_up_answer(self.client, model, self.active_investigation or {}, question)
                self.events.put(("answer_done", (question, answer)))
            except Exception as exc:
                self.events.put(("answer_error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _append_chat_message(self, role: str, text: str) -> None:
        self.chat_history.append({"role": role, "content": text})
        row = tk.Frame(self.chat_messages, bg=PANEL)
        row.pack(fill="x", pady=(7, 0))
        is_user = role == "user"
        bg = BLUE_LIGHT if is_user else "#f6f7f9"
        fg = INK
        label = "You" if is_user else "BioDetective · local model"
        bubble = tk.Frame(row, bg=bg, padx=12, pady=10)
        bubble.pack(side="right" if is_user else "left", anchor="e" if is_user else "w", fill="x")
        tk.Label(bubble, text=label, font=self._font(8, "bold"), bg=bg, fg=BLUE if is_user else MUTED).pack(anchor="w")
        tk.Label(bubble, text=text, font=self._font(9), bg=bg, fg=fg, wraplength=730, justify="left").pack(anchor="w", pady=(4, 0))

    def _set_chat_busy(self, busy: bool) -> None:
        if not hasattr(self, "chat_button"):
            return
        self.chat_button.configure(state="disabled" if busy else "normal", text="Thinking…" if busy else "Ask  →")
        self.chat_entry.configure(state="disabled" if busy else "normal")

    def _export_report(self) -> None:
        if not self.active_investigation:
            return
        filename = f"BioDetective_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        path = filedialog.asksaveasfilename(
            title="Export BioDetective report",
            defaultextension=".md",
            initialfile=filename,
            filetypes=[("Markdown report", "*.md"), ("Text file", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as output:
                output.write(report_markdown(self.active_investigation))
            messagebox.showinfo("Report exported", f"Saved report to:\n{path}")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))

    def _load_investigation(self, record_id: str) -> None:
        data = self.store.load(record_id)
        if not data:
            return
        self.active_id = record_id
        self.chat_history = []
        self.top_title.configure(text="Saved investigation")
        self._render_results(data)

    def new_investigation(self) -> None:
        self._render_home()

    def _show_about(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("About BioDetective")
        win.transient(self.root)
        win.configure(bg=PANEL)
        win.geometry("520x440")
        win.resizable(False, False)
        body = tk.Frame(win, bg=PANEL, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        tk.Label(body, text=f"{APP_NAME}  ·  v{APP_VERSION}", font=self._font(16, "bold"), bg=PANEL, fg=INK).pack(anchor="w")
        text = (
            "BioDetective investigates biological claims using local-model-assisted claim analysis, literature retrieval, "
            "source-linked evidence cards, and a prototype evidence graph.\n\n"
            "LOCAL INFERENCE\nModel prompts and retrieved abstracts are processed by Ollama on this computer. BioDetective does not use a cloud-model API.\n\n"
            "NETWORK USE\nLiterature queries and search terms are sent to Europe PMC to retrieve public bibliographic records and abstracts.\n\n"
            "DATA STORAGE\nInvestigation history is stored locally in %LOCALAPPDATA%\\BioDetective.\n\n"
            "SCIENTIFIC LIMITS\nEvidence labels are model-proposed and require review. The pilot BES is a weighted balance of classified retrieved records, not a truth probability or validated scientific measure. Search results are not exhaustive."
        )
        tk.Label(body, text=text, font=self._font(10), bg=PANEL, fg=MUTED, wraplength=465, justify="left").pack(anchor="w", pady=(14, 18))
        tk.Button(body, text="Get Ollama for Windows ↗", command=lambda: webbrowser.open("https://ollama.com/download/windows"), relief="flat", bd=0, bg=BLUE_LIGHT, fg=BLUE, padx=12, pady=8, cursor="hand2").pack(anchor="w")

    def _show_about_version(self) -> None:
        self._show_about()


def main() -> None:
    root = tk.Tk()
    BioDetectiveApp(root)
    root.mainloop()

