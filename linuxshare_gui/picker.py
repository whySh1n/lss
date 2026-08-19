"""Screen / window picker widget.

GTK is imported at module load, so this module is only imported by the
running GUI (never by the headless unit tests).
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import capture as gui_capture  # noqa: E402


class PickerWidget(Gtk.Box):
    """Displays selectable monitor cards and (on X11) a window list."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.session_type = gui_capture.detect_session_type()
        self._selected_display = None
        self._selected_window = None
        self._monitor_buttons: list[Gtk.ToggleButton] = []

        self._build_monitor_section()
        self._build_window_section()

    # -- Monitors --------------------------------------------------------

    def _build_monitor_section(self) -> None:
        header = Gtk.Label(xalign=0)
        header.set_markup("<b>Monitors</b>")
        self.append(header)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(3)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)

        displays = gui_capture.list_displays(self.session_type)
        group_leader: Gtk.ToggleButton | None = None
        for display in displays:
            label = (
                "Portal (choose at share time)"
                if display.name == "portal"
                else f"{display.name}\n{display.resolution}"
            )
            btn = Gtk.ToggleButton(label=label)
            if group_leader is None:
                group_leader = btn
            else:
                btn.set_group(group_leader)
            btn.connect("toggled", self._on_monitor_toggled, display)
            if display.primary:
                btn.set_active(True)
                self._selected_display = display
            self._monitor_buttons.append(btn)
            flow.append(btn)
        self.append(flow)

    def _on_monitor_toggled(self, button, display) -> None:  # noqa: ANN001
        if button.get_active():
            self._selected_display = display
            self._selected_window = None

    # -- Windows (X11 only) ---------------------------------------------

    def _build_window_section(self) -> None:
        header = Gtk.Label(xalign=0)
        header.set_markup("<b>Windows</b>")
        self.append(header)

        if self.session_type != "x11":
            note = Gtk.Label(xalign=0, wrap=True)
            note.set_markup(
                "<i>Individual window sharing is only available on X11. "
                "On Wayland, choose the screen/window in the system portal "
                "prompt that appears when you start sharing.</i>"
            )
            self.append(note)
            return

        windows = gui_capture.list_windows_x11()
        if not windows:
            self.append(Gtk.Label(label="No windows detected.", xalign=0))
            return

        scroller = Gtk.ScrolledWindow()
        scroller.set_min_content_height(120)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        for wid, title in windows:
            row = Gtk.ListBoxRow()
            row.window_id = wid  # type: ignore[attr-defined]
            row.set_child(Gtk.Label(label=title, xalign=0))
            listbox.append(row)
        listbox.connect("row-selected", self._on_window_selected)
        scroller.set_child(listbox)
        self.append(scroller)

    def _on_window_selected(self, listbox, row) -> None:  # noqa: ANN001
        if row is not None:
            self._selected_window = getattr(row, "window_id", None)
            for btn in self._monitor_buttons:
                btn.set_active(False)

    # -- Accessors -------------------------------------------------------

    def get_selected_display(self):
        """Return the currently selected Display (or None)."""
        return self._selected_display

    def get_selected_window(self):
        """Return the currently selected X11 window id (or None)."""
        return self._selected_window
