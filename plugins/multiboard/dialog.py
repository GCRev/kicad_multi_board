"""The export window (wxPython): a summary, the report in a text view, and an Export button.

It opens on a dry-run plan of the open board; Export runs that same plan, and Refresh takes a new snapshot.
Imported by ``ipc.run_ui``, which falls back to a report file when wxPython is missing.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Optional

import wx

from . import exporter, report
from .ipc import KiCadSession
from .plan import Plan
from .runner import RunResult, execute, exit_code, run_pipeline
from .summary import Summary, summarize

TITLE = "Multi-Board Fabrication Export"
FIELDS = (("board_file", "Board file"), ("output_root", "Output root"), ("kicad_cli", "kicad-cli"))


class ExportDialog(wx.Dialog):
    def __init__(self, runner: exporter.Runner) -> None:
        super().__init__(None, title=TITLE, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._runner = runner
        self._scratch = Path(tempfile.mkdtemp(prefix="multiboard-"))
        self._plan: Optional[Plan] = None
        self._summary: Optional[Summary] = None
        self._busy = False
        self.exit_code = 0
        self._build()
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._start_analysis()

    def _build(self) -> None:
        self._values: dict[str, wx.StaticText] = {}
        grid = wx.FlexGridSizer(2, 4, 12)
        grid.AddGrowableCol(1)
        for key, label in FIELDS:
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            value = wx.StaticText(self, style=wx.ST_ELLIPSIZE_MIDDLE)
            self._values[key] = value
            grid.Add(value, 1, wx.EXPAND)

        bold = self.GetFont().Bold()
        self._counts = wx.StaticText(self)
        self._counts.SetFont(bold)
        self._status = wx.StaticText(self, style=wx.ST_ELLIPSIZE_END)
        self._status.SetFont(bold)
        self._gauge = wx.Gauge(self, range=100, style=wx.GA_HORIZONTAL)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda _event: self._gauge.Pulse(), self._timer)

        self._text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP | wx.TE_RICH2)
        self._text.SetFont(wx.Font(wx.FontInfo(10).Family(wx.FONTFAMILY_TELETYPE)))
        # The rich-edit control keeps its own colours unless told.
        self._text.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
        self._text.SetForegroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT))

        self._copy = wx.Button(self, label="Copy")
        self._refresh = wx.Button(self, label="Refresh")
        self._export = wx.Button(self, label="Export")
        self._close = wx.Button(self, wx.ID_CANCEL, "Close")
        self._copy.Bind(wx.EVT_BUTTON, self._on_copy)
        self._refresh.Bind(wx.EVT_BUTTON, lambda _event: self._start_analysis())
        self._export.Bind(wx.EVT_BUTTON, self._on_export)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(self._copy, 0, wx.RIGHT, 6)
        buttons.Add(self._refresh)
        buttons.AddStretchSpacer()
        buttons.Add(self._export, 0, wx.RIGHT, 6)
        buttons.Add(self._close)

        root = wx.BoxSizer(wx.VERTICAL)
        root.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        root.Add(self._counts, 0, wx.LEFT | wx.RIGHT, 12)
        root.Add(self._status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
        root.Add(self._gauge, 0, wx.EXPAND | wx.ALL, 12)
        root.Add(self._text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        root.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizer(root)
        self.SetMinSize(wx.Size(760, 560))
        self.SetSize(wx.Size(900, 680))
        self.CenterOnScreen()

    def _set_busy(self, message: str) -> None:
        self._busy = True
        self._status.SetLabel(message)
        for button in (self._export, self._refresh, self._close):
            button.Enable(False)
        self._gauge.Show()
        self._timer.Start(80)
        self.Layout()

    def _set_idle(self, can_export: bool) -> None:
        self._busy = False
        self._timer.Stop()
        self._gauge.Hide()
        self._export.Enable(can_export)
        self._refresh.Enable(True)
        self._close.Enable(True)
        self.Layout()

    def _show(self, summary: Summary, text: str) -> None:
        self._summary = summary
        for key, _label in FIELDS:
            value = getattr(summary, key)
            self._values[key].SetLabel(value)
            self._values[key].SetToolTip(value)
        self._counts.SetLabel(summary.counts_line())
        self._status.SetLabel(summary.status)
        self._text.SetValue(text)
        self._text.SetInsertionPoint(0)
        self._text.ShowPosition(0)

    def _start_analysis(self) -> None:
        self._plan = self._summary = None
        self._export.SetLabel("Export")
        for value in self._values.values():
            value.SetLabel("")
        self._counts.SetLabel("")
        self._text.SetValue("")
        self._set_busy("Analysing the open board...")
        threading.Thread(target=self._analyse, daemon=True).start()

    def _analyse(self) -> None:
        try:
            shutil.rmtree(self._scratch, ignore_errors=True)
            self._scratch.mkdir(parents=True)
            snapshot, cli = KiCadSession().snapshot(self._scratch)
            plan, _ = run_pipeline(snapshot, cli, True, self._scratch / "work", runner=self._runner)
            wx.CallAfter(self._analysed, plan, report.render(plan, None, True))
        except Exception:  # noqa: BLE001 - the user only sees this window, so failures must reach it
            wx.CallAfter(self._failed, traceback.format_exc())

    def _analysed(self, plan: Plan, text: str) -> None:
        self._plan = plan
        summary = summarize(plan)
        self.exit_code = exit_code(plan, None)
        self._show(summary, text)
        self._set_idle(summary.can_export)

    def _on_export(self, _event: wx.CommandEvent) -> None:
        if self._plan is None:
            return
        self._set_busy("Exporting...")
        threading.Thread(target=self._do_export, args=(self._plan,), daemon=True).start()

    def _do_export(self, plan: Plan) -> None:
        try:
            result = execute(plan, self._scratch / "work", self._runner)
            wx.CallAfter(self._exported, plan, result, report.render(plan, result, False))
        except Exception:  # noqa: BLE001 - see _analyse
            wx.CallAfter(self._failed, traceback.format_exc())

    def _exported(self, plan: Plan, result: RunResult, text: str) -> None:
        summary = summarize(plan, result)
        self.exit_code = exit_code(plan, result)
        self._show(summary, text)
        self._export.SetLabel("Export again")
        self._set_idle(summary.can_export)

    def _failed(self, trace: str) -> None:
        self.exit_code = 3
        self._status.SetLabel("Failed unexpectedly. See the report below.")
        self._text.SetValue("Multi-board fabrication export failed unexpectedly:\n\n" + trace)
        # A failed export can be retried on the same plan; a failed analysis has no plan to export.
        self._set_idle(self._plan is not None and self._summary is not None and self._summary.can_export)

    def _on_copy(self, _event: wx.CommandEvent) -> None:
        if wx.TheClipboard.Open():
            try:
                wx.TheClipboard.SetData(wx.TextDataObject(self._text.GetValue()))
            finally:
                wx.TheClipboard.Close()

    def _on_close(self, event: wx.CloseEvent) -> None:
        if self._busy:  # a worker thread is still using the scratch folder
            event.Veto()
        else:
            event.Skip()

    def cleanup(self) -> None:
        self._timer.Stop()
        shutil.rmtree(self._scratch, ignore_errors=True)


def _follow_system_theme() -> None:
    """Follow the system dark/light theme; wxMSW needs to be asked, and KiCad's setting does not reach this process."""
    enable = getattr(wx.App, "MSWEnableDarkMode", None)
    if enable is not None:
        try:
            enable(wx.GetApp())
        except Exception:  # noqa: BLE001 - cosmetic only
            pass


def run(runner: exporter.Runner = exporter.run) -> int:
    """Show the window until it is closed. Returns the exit code of the last analysis or export."""
    app = wx.App(False)
    _follow_system_theme()  # before any window exists
    dialog = ExportDialog(runner)
    try:
        dialog.Raise()
        dialog.RequestUserAttention()
        dialog.ShowModal()
        return dialog.exit_code
    finally:
        dialog.cleanup()
        dialog.Destroy()
        del app
