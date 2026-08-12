"""A dependency-free desktop workflow for converting SOP Markdown to BPMN.

Run this module with ``py src/sop_to_bpmn_ui.py``.  The controller is kept
independent of Tk so its workflow and overwrite safeguards can be tested
without a graphical display.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TypeVar

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import ir_to_bpmn
from ir import load_bundle
from markdown_extractor import extract_markdown
from semantic_handoff import build_semantic_prompt, parse_semantic_response
from sop_to_ir import default_ir_path


class WorkflowError(ValueError):
    """An actionable error while preparing or building a BPMN bundle."""


class IRResponseValidationError(WorkflowError):
    """Raised when the submitted semantic response fails IR validation."""


class OverwriteRequired(WorkflowError):
    """Raised before an existing generated artifact would be replaced."""

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        super().__init__("The following files already exist:\n" + "\n".join(
            str(path) for path in paths
        ))


@dataclass(frozen=True)
class SourcePreparation:
    source: Path
    prompt: str
    ir_path: Path
    has_existing_ir: bool


@dataclass(frozen=True)
class BuildResult:
    paths: tuple[Path, ...]


def build_ir_validation_feedback(response: str, error: object) -> str:
    """Build a correction prompt containing an IR validation error and raw response."""

    response_suffix = "" if response.endswith("\n") else "\n"
    return (
        "Please correct the submitted IR so that it passes validation. "
        "Return only the corrected IR JSON object.\n\n"
        "Validation error:\n"
        f"{error}\n\n"
        "Submitted response (raw):\n"
        "--- BEGIN SUBMITTED RESPONSE ---\n"
        + response
        + response_suffix
        + "--- END SUBMITTED RESPONSE ---"
    )


class SOPToBPMNController:
    """Stateful, UI-neutral facade over the existing SOP-to-BPMN modules."""

    def __init__(self) -> None:
        self.source: Path | None = None
        self.prompt = ""
        self.ir_path: Path | None = None

    def prepare_source(self, source: str | Path) -> SourcePreparation:
        source_path = Path(source)
        if source_path.suffix.lower() != ".md":
            raise WorkflowError("Select a Markdown (.md) file.")
        try:
            extraction = extract_markdown(source_path)
            prompt = build_semantic_prompt(extraction)
        except (OSError, ValueError) as exc:
            raise WorkflowError(str(exc)) from exc

        self.source = source_path
        self.prompt = prompt
        self.ir_path = None
        candidate = default_ir_path(source_path)
        return SourcePreparation(
            source=source_path,
            prompt=prompt,
            ir_path=candidate,
            has_existing_ir=candidate.exists(),
        )

    def use_existing_ir(self) -> Path:
        if self.source is None:
            raise WorkflowError("Select and validate a Markdown file first.")
        candidate = default_ir_path(self.source)
        if not candidate.exists():
            raise WorkflowError(f"No adjacent IR file was found: {candidate.name}")
        try:
            load_bundle([candidate])
        except (OSError, ValueError) as exc:
            raise WorkflowError(f"Existing IR is not valid: {exc}") from exc
        self.ir_path = candidate
        return candidate

    def save_semantic_response(self, response: str, *, overwrite: bool = False) -> Path:
        if self.source is None:
            raise WorkflowError("Select and validate a Markdown file first.")
        try:
            document = parse_semantic_response(response)
            load_bundle([document])
        except (TypeError, ValueError) as exc:
            raise IRResponseValidationError(
                f"Semantic response failed IR validation: {exc}"
            ) from exc

        destination = default_ir_path(self.source)
        if destination.exists() and not overwrite:
            raise OverwriteRequired([destination])
        try:
            destination.write_text(
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise WorkflowError(f"Could not write IR {destination}: {exc}") from exc
        self.ir_path = destination
        return destination

    def planned_outputs(self) -> list[Path]:
        if self.source is None or self.ir_path is None:
            raise WorkflowError("Validate or save an IR before building BPMN.")
        try:
            return ir_to_bpmn.planned_output_paths(
                [self.ir_path], output_dir=self.source.parent
            )
        except ir_to_bpmn.CLIError as exc:
            raise WorkflowError(str(exc)) from exc

    def build_bpmn(self, *, overwrite: bool = False) -> BuildResult:
        planned = self.planned_outputs()
        existing = [path for path in planned if path.exists()]
        if existing and not overwrite:
            raise OverwriteRequired(existing)
        assert self.source is not None and self.ir_path is not None
        try:
            paths = ir_to_bpmn.run([self.ir_path], output_dir=self.source.parent)
        except ir_to_bpmn.CLIError as exc:
            raise WorkflowError(str(exc)) from exc
        return BuildResult(tuple(paths))


ResultT = TypeVar("ResultT")


class SOPToBPMNApp:
    """Tk presentation layer for :class:`SOPToBPMNController`."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.controller = SOPToBPMNController()
        self.busy = False
        self.ir_validation_feedback = ""
        self.source_var = tk.StringVar(value="No Markdown file selected")
        self.status_var = tk.StringVar(value="1. Select a Markdown SOP file.")
        self.existing_ir_var = tk.StringVar(value="")
        self._build_window()
        self._refresh_controls()

    def _build_window(self) -> None:
        self.root.title("SOP Markdown to BPMN")
        self.root.minsize(760, 650)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text="SOP Markdown to BPMN", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        source_frame = ttk.LabelFrame(frame, text="1. Select and validate Markdown", padding=10)
        source_frame.grid(row=1, column=0, sticky="ew", pady=(12, 8))
        source_frame.columnconfigure(0, weight=1)
        ttk.Label(source_frame, textvariable=self.source_var, wraplength=620).grid(
            row=0, column=0, sticky="w"
        )
        self.browse_button = ttk.Button(source_frame, text="Browse…", command=self._browse)
        self.browse_button.grid(row=0, column=1, padx=(10, 0))
        self.validate_button = ttk.Button(source_frame, text="Validate template", command=self._prepare_source)
        self.validate_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.existing_ir_button = ttk.Button(source_frame, text="Use existing IR", command=self._use_existing_ir)
        self.existing_ir_button.grid(row=1, column=1, padx=(10, 0), pady=(8, 0))
        ttk.Label(source_frame, textvariable=self.existing_ir_var, wraplength=620).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        prompt_frame = ttk.LabelFrame(frame, text="2. Create or review semantic IR", padding=10)
        prompt_frame.grid(row=2, column=0, sticky="nsew", pady=8)
        prompt_frame.columnconfigure(0, weight=1)
        ttk.Label(prompt_frame, text="Semantic prompt (use with your approved modeling process):").grid(row=0, column=0, sticky="w")
        self.prompt_box = scrolledtext.ScrolledText(prompt_frame, height=7, wrap=tk.WORD, state=tk.DISABLED)
        self.prompt_box.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        prompt_buttons = ttk.Frame(prompt_frame)
        prompt_buttons.grid(row=2, column=0, sticky="w")
        self.copy_button = ttk.Button(prompt_buttons, text="Copy prompt", command=self._copy_prompt)
        self.copy_button.grid(row=0, column=0)
        self.save_prompt_button = ttk.Button(prompt_buttons, text="Save prompt…", command=self._save_prompt)
        self.save_prompt_button.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(prompt_frame, text="Paste the returned IR JSON, or load it from a file:").grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.response_box = scrolledtext.ScrolledText(prompt_frame, height=7, wrap=tk.WORD)
        self.response_box.grid(row=4, column=0, sticky="ew", pady=(4, 6))
        self.response_box.bind("<<Modified>>", self._response_modified)
        self.response_box.edit_modified(False)
        response_buttons = ttk.Frame(prompt_frame)
        response_buttons.grid(row=5, column=0, sticky="w")
        self.load_response_button = ttk.Button(response_buttons, text="Load JSON…", command=self._load_response)
        self.load_response_button.grid(row=0, column=0)
        self.save_ir_button = ttk.Button(response_buttons, text="Validate and save IR", command=self._save_ir)
        self.save_ir_button.grid(row=0, column=1, padx=(8, 0))

        build_frame = ttk.LabelFrame(frame, text="3. Build BPMN", padding=10)
        build_frame.grid(row=3, column=0, sticky="ew", pady=8)
        self.build_button = ttk.Button(build_frame, text="Build and validate BPMN", command=self._build_bpmn)
        self.build_button.grid(row=0, column=0, sticky="w")
        self.results = tk.Listbox(build_frame, height=4)
        self.results.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        status_frame = ttk.LabelFrame(frame, text="Status", padding=10)
        status_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, wraplength=700).grid(
            row=0, column=0, sticky="w"
        )
        self.copy_status_button = ttk.Button(
            status_frame, text="Copy status", command=self._copy_status
        )
        self.copy_status_button.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.copy_feedback_button = ttk.Button(
            status_frame, text="Copy IR feedback", command=self._copy_ir_feedback
        )
        self.copy_feedback_button.grid(row=2, column=0, sticky="w", pady=(8, 0))

    def _refresh_controls(self) -> None:
        prepared = self.controller.source is not None and bool(self.controller.prompt)
        has_ir = self.controller.ir_path is not None
        normal = tk.NORMAL if not self.busy else tk.DISABLED
        self.browse_button.configure(state=normal)
        self.validate_button.configure(state=normal if self.controller.source else tk.DISABLED)
        candidate = self.controller.source and default_ir_path(self.controller.source).exists()
        self.existing_ir_button.configure(state=normal if candidate and prepared else tk.DISABLED)
        for button in (self.copy_button, self.save_prompt_button, self.load_response_button, self.save_ir_button):
            button.configure(state=normal if prepared else tk.DISABLED)
        self.copy_status_button.configure(state=tk.NORMAL)
        self.copy_feedback_button.configure(
            state=normal if prepared and self.ir_validation_feedback else tk.DISABLED
        )
        self.build_button.configure(state=normal if has_ir else tk.DISABLED)

    def _set_prompt(self, prompt: str) -> None:
        self.prompt_box.configure(state=tk.NORMAL)
        self.prompt_box.delete("1.0", tk.END)
        self.prompt_box.insert("1.0", prompt)
        self.prompt_box.configure(state=tk.DISABLED)

    def _response_modified(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        if not self.response_box.edit_modified():
            return
        self.response_box.edit_modified(False)
        if self.ir_validation_feedback:
            self._clear_ir_validation_feedback()

    def _browse(self) -> None:
        filename = filedialog.askopenfilename(
            title="Select SOP Markdown", filetypes=[("Markdown", "*.md"), ("All files", "*.*")]
        )
        if filename:
            self.controller = SOPToBPMNController()
            # Keep the selection separate from successful template preparation:
            # controls still require a non-empty prompt before later steps open.
            self.controller.source = Path(filename)
            self.source_var.set(filename)
            self.existing_ir_var.set("")
            self._set_prompt("")
            self.response_box.delete("1.0", tk.END)
            self._clear_ir_validation_feedback()
            self.results.delete(0, tk.END)
            self.status_var.set("Click ‘Validate template’ to continue.")
            self._refresh_controls()

    def _run_async(self, work: Callable[[], ResultT], done: Callable[[ResultT | None, Exception | None], None]) -> None:
        self.busy = True
        self.status_var.set("Working…")
        self._refresh_controls()
        completed: queue.Queue[tuple[ResultT | None, Exception | None]] = queue.Queue()

        def runner() -> None:
            try:
                completed.put((work(), None))
            except Exception as exc:  # returned to Tk's main thread below
                completed.put((None, exc))

        threading.Thread(target=runner, daemon=True).start()

        def poll() -> None:
            try:
                result, error = completed.get_nowait()
            except queue.Empty:
                self.root.after(40, poll)
                return
            self.busy = False
            done(result, error)
            self._refresh_controls()

        self.root.after(40, poll)

    def _prepare_source(self) -> None:
        if self.controller.source is None:
            messagebox.showinfo("Select Markdown", "Choose a Markdown file first.")
            return
        source = self.controller.source

        def done(result: SourcePreparation | None, error: Exception | None) -> None:
            if error:
                self.status_var.set(f"Template validation failed: {error}")
                return
            assert result is not None
            self._set_prompt(result.prompt)
            if result.has_existing_ir:
                self.existing_ir_var.set(f"An adjacent IR was found: {result.ir_path.name}. You may validate and use it.")
            else:
                self.existing_ir_var.set("No adjacent IR found. Copy the prompt, then paste or load the returned JSON.")
            self.status_var.set("Template is valid. Continue with the semantic IR step.")

        self._run_async(lambda: self.controller.prepare_source(source), done)

    def _use_existing_ir(self) -> None:
        def done(result: Path | None, error: Exception | None) -> None:
            if error:
                self.status_var.set(str(error))
                return
            assert result is not None
            self.status_var.set(f"Existing IR is valid: {result.name}. You can now build BPMN.")

        self._run_async(self.controller.use_existing_ir, done)

    def _copy_prompt(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.controller.prompt)
        self.status_var.set("Semantic prompt copied to the clipboard.")

    def _copy_status(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self.status_var.get())

    def _copy_ir_feedback(self) -> None:
        if not self.ir_validation_feedback:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.ir_validation_feedback)
        self.status_var.set("IR validation feedback copied to the clipboard.")

    def _clear_ir_validation_feedback(self) -> None:
        self.ir_validation_feedback = ""
        if hasattr(self, "copy_feedback_button"):
            self._refresh_controls()

    def _save_prompt(self) -> None:
        if self.controller.source is None:
            return
        default = self.controller.source.with_suffix(".semantic-prompt.txt").name
        destination = filedialog.asksaveasfilename(
            title="Save semantic prompt", initialdir=self.controller.source.parent,
            initialfile=default, defaultextension=".txt", filetypes=[("Text", "*.txt")]
        )
        if not destination:
            return
        try:
            Path(destination).write_text(self.controller.prompt, encoding="utf-8")
        except OSError as exc:
            self.status_var.set(f"Could not save prompt: {exc}")
            return
        self.status_var.set(f"Saved semantic prompt to {Path(destination).name}.")

    def _load_response(self) -> None:
        filename = filedialog.askopenfilename(
            title="Load semantic IR JSON", filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not filename:
            return

        def done(result: str | None, error: Exception | None) -> None:
            if error:
                self.status_var.set(f"Could not load JSON: {error}")
                return
            self.response_box.delete("1.0", tk.END)
            self.response_box.insert("1.0", result or "")
            self._clear_ir_validation_feedback()
            self.status_var.set("Loaded semantic response. Validate it before building BPMN.")

        self._run_async(lambda: Path(filename).read_text(encoding="utf-8"), done)

    def _save_ir(self, *, overwrite: bool = False) -> None:
        response = self.response_box.get("1.0", tk.END)
        self._clear_ir_validation_feedback()

        def done(result: Path | None, error: Exception | None) -> None:
            if isinstance(error, OverwriteRequired):
                if messagebox.askyesno("Replace existing IR?", f"Replace this file?\n\n{error.paths[0]}"):
                    self._save_ir(overwrite=True)
                else:
                    self.status_var.set("IR was not replaced.")
                return
            if error:
                if isinstance(error, IRResponseValidationError):
                    self.ir_validation_feedback = build_ir_validation_feedback(response, error)
                self.status_var.set(str(error))
                return
            assert result is not None
            self._clear_ir_validation_feedback()
            self.status_var.set(f"IR is valid and saved as {result.name}. You can now build BPMN.")

        self._run_async(lambda: self.controller.save_semantic_response(response, overwrite=overwrite), done)

    def _build_bpmn(self, *, overwrite: bool = False) -> None:
        def done(result: BuildResult | None, error: Exception | None) -> None:
            if isinstance(error, OverwriteRequired):
                files = "\n".join(str(path) for path in error.paths)
                if messagebox.askyesno("Replace existing BPMN?", f"Replace these BPMN files?\n\n{files}"):
                    self._build_bpmn(overwrite=True)
                else:
                    self.status_var.set("BPMN files were not replaced.")
                return
            if error:
                self.status_var.set(f"BPMN build failed: {error}")
                return
            assert result is not None
            self.results.delete(0, tk.END)
            for path in result.paths:
                self.results.insert(tk.END, path.name)
            count = len(result.paths)
            self.status_var.set(f"Built and validated {count} BPMN file{'s' if count != 1 else ''}.")
            assert self.controller.source is not None
            try:
                os.startfile(str(self.controller.source.parent))
            except OSError as exc:
                self.status_var.set(self.status_var.get() + f" Could not open output folder: {exc}")

        self._run_async(lambda: self.controller.build_bpmn(overwrite=overwrite), done)


def main() -> None:
    root = tk.Tk()
    SOPToBPMNApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
