"""Main application window (GTK4 / libadwaita)."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

try:  # libadwaita is optional
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: E402

    _HAVE_ADW = True
except (ValueError, ImportError):  # pragma: no cover
    _HAVE_ADW = False

from . import __version__  # noqa: E402
from . import capture as gui_capture  # noqa: E402
from . import settings as gui_settings  # noqa: E402
from .picker import PickerWidget  # noqa: E402

_BaseWindow = Adw.ApplicationWindow if _HAVE_ADW else Gtk.ApplicationWindow


class MainWindow(_BaseWindow):  # type: ignore[misc, valid-type]
    """Primary window: picker, start/stop control and status bar."""

    def __init__(self, application) -> None:  # noqa: ANN001
        super().__init__(application=application)
        self.set_title("LinuxShare")
        self.set_default_size(560, 520)

        self.call_process = None
        self.config = gui_settings.load_config()
        self.controller = gui_capture.CaptureController()
        self.controller.on_state_change = self._on_state_change_threadsafe

        self._build_ui()
        self.connect("close-request", self._on_close_request)

    # -- UI construction -------------------------------------------------

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Gtk.HeaderBar()
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Settings", "app.settings")
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        if _HAVE_ADW:
            self.set_content(root)
            root.append(header)
        else:
            self.set_titlebar(header)
            self.set_child(root)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_margin_top(16)
        body.set_margin_bottom(16)
        body.set_margin_start(16)
        body.set_margin_end(16)
        root.append(body)

        private_button = Gtk.Button(label="Open private screen & voice call")
        private_button.add_css_class("suggested-action")
        private_button.connect("clicked", self._on_private_call)
        body.append(private_button)
        note = Gtk.Label(
            label="Calls run in your browser. End or close the host tab to revoke access.",
            wrap=True,
            xalign=0,
        )
        body.append(note)
        body.append(Gtk.Separator())
        body.append(Gtk.Label(label="Virtual camera (Teams / Zoom)", xalign=0))
        self.picker = PickerWidget()
        body.append(self.picker)

        self.share_button = Gtk.Button(label="Start sharing")
        self.share_button.add_css_class("suggested-action")
        self.share_button.connect("clicked", self._on_share_clicked)
        body.append(self.share_button)

        self.status_label = Gtk.Label(xalign=0)
        self.status_label.set_markup("<i>Idle</i>")
        body.append(self.status_label)

    def _on_private_call(self, _button):
        from linuxshare_calls.launcher import open_call

        try:
            if self.call_process is not None and self.call_process.poll() is None:
                self._set_status("Local call service is already open in your browser")
                return
            self.call_process = open_call()
            self._set_status(
                "Private-call page opened. Approve your guest in the browser."
            )
        except (OSError, RuntimeError, ValueError) as exc:
            self._set_status(str(exc), error=True)

    def close_private_calls(self):
        from linuxshare_calls.launcher import close_call

        close_call(self.call_process)
        self.call_process = None

    # -- Sharing control -------------------------------------------------

    def _on_share_clicked(self, _button) -> None:  # noqa: ANN001
        if self.controller.is_sharing():
            self.stop_sharing()
        else:
            self.start_sharing()

    def start_sharing(self) -> None:
        display = self.picker.get_selected_display()
        window_id = self.picker.get_selected_window()
        self.share_button.set_sensitive(False)
        self._set_status("Starting...")
        # Run start in a thread so the UI stays responsive.
        import threading

        threading.Thread(
            target=self.controller.start,
            kwargs={
                "display": display,
                "window_id": window_id,
                "fps": self.config.fps,
                "device": self.config.device or None,
            },
            daemon=True,
        ).start()

    def stop_sharing(self) -> None:
        import threading

        threading.Thread(target=self.controller.stop, daemon=True).start()

    # -- State updates (thread-safe) -------------------------------------

    def _on_state_change_threadsafe(self, state: str, message: str) -> None:
        GLib.idle_add(self._apply_state, state, message)

    def _on_close_request(self, *_args):
        self.controller.shutdown()
        self.close_private_calls()
        self.get_application().quit()
        return False

    def _apply_state(self, state: str, message: str) -> bool:
        self.share_button.set_sensitive(True)
        self.picker.set_sensitive(
            state
            not in (
                gui_capture.CaptureController.STATE_STARTING,
                gui_capture.CaptureController.STATE_SHARING,
            )
        )
        if self.get_application().tray:
            self.get_application().tray.set_sharing(
                state == gui_capture.CaptureController.STATE_SHARING
            )
        if state == gui_capture.CaptureController.STATE_SHARING:
            self.share_button.set_label("Stop sharing")
            self._set_status(f"Sharing on {message}")
        elif state == gui_capture.CaptureController.STATE_STARTING:
            self.share_button.set_label("Cancel sharing")
            self._set_status(message)
        elif state == gui_capture.CaptureController.STATE_ERROR:
            self.share_button.set_label("Start sharing")
            self._set_status(f"Error: {message}", error=True)
        else:
            self.share_button.set_label("Start sharing")
            self._set_status("Idle")
        return False  # remove from idle queue

    def _set_status(self, text: str, error: bool = False) -> None:
        markup = (
            f"<span foreground='red'>{GLib.markup_escape_text(text)}</span>"
            if error
            else f"<i>{GLib.markup_escape_text(text)}</i>"
        )
        self.status_label.set_markup(markup)

    # -- Dialogs ---------------------------------------------------------

    def open_settings(self) -> None:
        dialog = gui_settings.build_settings_dialog(
            self, self.config, self._on_settings_saved
        )
        dialog.present()

    def _on_settings_saved(self, new_config) -> None:  # noqa: ANN001
        self.config = new_config

    def open_about(self) -> None:
        about_kwargs = dict(
            application_name="LinuxShare",
            version=__version__,
            developer_name="LinuxShare Contributors",
            license_type=Gtk.License.MIT_X11,
            website="https://github.com/whySh1n/linux-screen-share",
            comments="Share your Linux screen as a virtual webcam.",
        )
        if _HAVE_ADW and hasattr(Adw, "AboutWindow"):
            about = Adw.AboutWindow(transient_for=self, **about_kwargs)
            about.present()
        else:  # pragma: no cover
            about = Gtk.AboutDialog(
                transient_for=self,
                modal=True,
                program_name="LinuxShare",
                version=__version__,
                license_type=Gtk.License.MIT_X11,
                website="https://github.com/whySh1n/linux-screen-share",
                comments="Share your Linux screen as a virtual webcam.",
            )
            about.present()
