"""Tkinter GUI for the Moondrop CHU 2 DSP tool.

A no-dependency graphical editor for authoring and previewing EQ presets. It
reads/writes the same JSON preset format as the CLI and, when a device is
present, reports its status. DSP upload is intentionally deferred until the
wire protocol is reverse-engineered.
"""

from __future__ import annotations

import math
import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from . import __version__, device as device_mod, eq, preset


class Chu2App(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"Moondrop CHU 2 DSP Tool {__version__}")
        self.geometry("880x640")
        self.minsize(720, 520)

        self.preset_path: Optional[str] = None
        self.current = preset.flat_preset()

        self._build_widgets()
        self._refresh_band_list()
        self._refresh_response()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_widgets(self) -> None:
        # Device status bar.
        status = ttk.Frame(self, padding=(8, 6))
        status.pack(fill="x")
        self.device_label = ttk.Label(status, text="Device: checking…")
        self.device_label.pack(side="left")
        ttk.Button(status, text="Rescan", command=self._rescan).pack(side="right")
        self._rescan()

        # Main split: band editor (left) and response plot (right).
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8, pady=4)

        editor = ttk.LabelFrame(body, text="EQ bands", padding=6)
        editor.pack(side="left", fill="both", expand=True)
        self._build_editor(editor)

        plot = ttk.LabelFrame(body, text="Frequency response", padding=6)
        plot.pack(side="right", fill="both", expand=True)
        self._build_plot(plot)

        # Preset controls at the bottom.
        presets = ttk.LabelFrame(self, text="Presets", padding=6)
        presets.pack(fill="x", padx=8, pady=4)
        self._build_presets(presets)

    def _build_editor(self, parent: ttk.Frame) -> None:
        columns = ("type", "freq", "gain", "q")
        self.band_tree = ttk.Treeview(parent, columns=columns, show="headings", height=10)
        for col, width, text in (
            ("type", 90, "Type"),
            ("freq", 90, "Freq (Hz)"),
            ("gain", 70, "Gain (dB)"),
            ("q", 60, "Q"),
        ):
            self.band_tree.heading(col, text=text)
            self.band_tree.column(col, width=width, anchor="center")
        self.band_tree.pack(fill="both", expand=True)
        self.band_tree.bind("<Double-1>", lambda _e: self._edit_band())

        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=4)
        ttk.Button(controls, text="Add", command=self._add_band).pack(side="left")
        ttk.Button(controls, text="Edit", command=self._edit_band).pack(side="left")
        ttk.Button(controls, text="Remove", command=self._remove_band).pack(side="left")

    def _build_plot(self, parent: ttk.Frame) -> None:
        self.canvas = tk.Canvas(parent, background="#0f1115", height=360)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._refresh_response())

    def _build_presets(self, parent: ttk.Frame) -> None:
        self.name_var = tk.StringVar(value=self.current.name)
        self.desc_var = tk.StringVar(value=self.current.description)
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="Name").pack(side="left")
        ttk.Entry(row, textvariable=self.name_var, width=30).pack(side="left", padx=4)
        ttk.Label(row, text="Description").pack(side="left", padx=(12, 0))
        ttk.Entry(row, textvariable=self.desc_var).pack(side="left", fill="x", expand=True, padx=4)

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Load…", command=self._load_preset).pack(side="left")
        ttk.Button(actions, text="Save…", command=self._save_preset).pack(side="left")
        ttk.Button(actions, text="Export EqualizerAPO…", command=self._export_apo).pack(side="left")
        ttk.Button(actions, text="New flat", command=self._new_preset).pack(side="left")

    # ------------------------------------------------------------------ #
    # Device
    # ------------------------------------------------------------------ #
    def _rescan(self) -> None:
        try:
            dev = device_mod.require_chu2()
            product = None
            try:
                product = dev.product
            except Exception:
                product = None
            self.device_label.config(
                text=f"Device: {product or 'Moondrop CHU 2'} found "
                f"(VID:{dev.idVendor:04X} PID:{dev.idProduct:04X})"
            )
        except device_mod.UsbError as exc:
            self.device_label.config(text="Device: not found")

    # ------------------------------------------------------------------ #
    # Band editing
    # ------------------------------------------------------------------ #
    def _refresh_band_list(self) -> None:
        self.band_tree.delete(*self.band_tree.get_children())
        for band in self.current.bands:
            self.band_tree.insert(
                "",
                "end",
                values=(band.type, f"{band.frequency:.0f}", f"{band.gain:.1f}", f"{band.q:.2f}"),
            )
        self._refresh_response()

    def _add_band(self) -> None:
        band = self._prompt_band(None)
        if band is not None:
            self.current.bands.append(band)
            self._refresh_band_list()

    def _edit_band(self) -> None:
        selection = self.band_tree.selection()
        if not selection:
            return
        index = self.band_tree.index(selection[0])
        band = self._prompt_band(self.current.bands[index])
        if band is not None:
            self.current.bands[index] = band
            self._refresh_band_list()

    def _remove_band(self) -> None:
        selection = self.band_tree.selection()
        if not selection:
            return
        index = self.band_tree.index(selection[0])
        del self.current.bands[index]
        self._refresh_band_list()

    def _prompt_band(self, band: Optional[eq.FilterBand]) -> Optional[eq.FilterBand]:
        dialog = tk.Toplevel(self)
        dialog.title("Edit band")
        dialog.transient(self)
        dialog.grab_set()

        ftype = tk.StringVar(value=band.type if band else "peaking")
        freq = tk.StringVar(value=f"{band.frequency:.0f}" if band else "1000")
        gain = tk.DoubleVar(value=band.gain if band else 0.0)
        q = tk.StringVar(value=f"{band.q:.2f}" if band else "1.0")

        grid = ttk.Frame(dialog, padding=12)
        grid.pack(fill="both", expand=True)
        ttk.Label(grid, text="Type").grid(row=0, column=0, sticky="w")
        ttk.Combobox(grid, textvariable=ftype, values=list(eq.FILTER_TYPES), state="readonly").grid(
            row=0, column=1, sticky="ew", pady=2
        )
        ttk.Label(grid, text="Frequency (Hz)").grid(row=1, column=0, sticky="w")
        ttk.Entry(grid, textvariable=freq).grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Label(grid, text="Gain (dB)").grid(row=2, column=0, sticky="w")
        ttk.Scale(grid, from_=-12, to=12, variable=gain, length=200).grid(
            row=2, column=1, sticky="ew", pady=2
        )
        ttk.Label(grid, text="Q").grid(row=3, column=0, sticky="w")
        ttk.Entry(grid, textvariable=q).grid(row=3, column=1, sticky="ew", pady=2)

        result: List[Optional[eq.FilterBand]] = [None]

        def ok() -> None:
            try:
                result[0] = eq.FilterBand(
                    type=ftype.get(),
                    frequency=float(freq.get()),
                    gain=float(gain.get()),
                    q=float(q.get()),
                )
            except ValueError as exc:
                messagebox.showerror("Invalid band", str(exc), parent=dialog)
                return
            dialog.destroy()

        buttons = ttk.Frame(grid)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="OK", command=ok).pack(side="left")

        self.wait_window(dialog)
        return result[0]

    # ------------------------------------------------------------------ #
    # Response plot
    # ------------------------------------------------------------------ #
    def _refresh_response(self) -> None:
        canvas = self.canvas
        if canvas.winfo_width() < 10:
            return
        canvas.delete("all")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        pad = 28

        # Axes.
        canvas.create_line(pad, pad, width - pad, pad, fill="#3a3f4a")  # 0 dB
        canvas.create_line(pad, pad, pad, height - pad, fill="#3a3f4a")
        for db in (-12, -6, 0, 6, 12):
            y = self._db_to_y(db, height, pad)
            canvas.create_line(pad, y, width - pad, y, fill="#23272f")
            canvas.create_text(pad - 4, y, text=f"{db}", anchor="e", fill="#8b93a3")

        freqs = eq.log_frequency_axis(20, 20000, 200)
        response = self.current.equalizer().magnitude_response_db(freqs)
        points = []
        for f, g in zip(freqs, response):
            x = pad + (math.log10(f) - math.log10(20)) / (math.log10(20000) - math.log10(20)) * (
                width - 2 * pad
            )
            y = self._db_to_y(g, height, pad)
            points.extend((x, y))
        if points:
            canvas.create_line(*points, fill="#4fc3f7", width=2, smooth=True)

    @staticmethod
    def _db_to_y(db: float, height: int, pad: int) -> float:
        # Map [-12, +12] dB onto the plotting area.
        span = height - 2 * pad
        return pad + span * (1 - (db + 12) / 24)

    # ------------------------------------------------------------------ #
    # Preset file operations
    # ------------------------------------------------------------------ #
    def _sync_name_fields(self) -> None:
        self.current.name = self.name_var.get().strip() or "Untitled"
        self.current.description = self.desc_var.get().strip()

    def _load_preset(self) -> None:
        path = filedialog.askopenfilename(
            title="Load preset",
            filetypes=[("JSON presets", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.current = preset.load(path)
        except preset.PresetError as exc:
            messagebox.showerror("Failed to load", str(exc))
            return
        self.preset_path = path
        self.name_var.set(self.current.name)
        self.desc_var.set(self.current.description)
        self._refresh_band_list()

    def _save_preset(self) -> None:
        self._sync_name_fields()
        path = filedialog.asksaveasfilename(
            title="Save preset",
            defaultextension=".json",
            filetypes=[("JSON presets", "*.json")],
        )
        if not path:
            return
        try:
            preset.save(self.current, path)
        except OSError as exc:
            messagebox.showerror("Failed to save", str(exc))
            return
        self.preset_path = path

    def _export_apo(self) -> None:
        self._sync_name_fields()
        path = filedialog.asksaveasfilename(
            title="Export EqualizerAPO config",
            defaultextension=".txt",
            filetypes=[("EqualizerAPO config", "*.txt")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(preset.to_equalizer_apo(self.current))
        except OSError as exc:
            messagebox.showerror("Failed to export", str(exc))

    def _new_preset(self) -> None:
        self.current = preset.flat_preset()
        self.preset_path = None
        self.name_var.set(self.current.name)
        self.desc_var.set(self.current.description)
        self._refresh_band_list()


def main(argv: Optional[List[str]] = None) -> int:
    try:
        app = Chu2App()
    except tk.TclError as exc:  # pragma: no cover - no display available
        print(f"error: cannot start GUI: {exc}", file=sys.stderr)
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
