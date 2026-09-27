"""Optional GTK3 indicator process; stdin EOF ends it with its parent."""
import sys


def main():
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import GLib, Gtk

    indicator_module = None
    for name in ("AyatanaAppIndicator3", "AppIndicator3"):
        try:
            gi.require_version(name, "0.1")
            indicator_module = getattr(__import__("gi.repository", fromlist=[name]), name)
            break
        except (ValueError, ImportError):
            continue
    if indicator_module is None:
        return 1
    indicator = indicator_module.Indicator.new(
        "linuxshare", sys.argv[1], indicator_module.IndicatorCategory.APPLICATION_STATUS)
    menu = Gtk.Menu()
    for label, action in (("Show window", "show"), ("Stop sharing", "stop"),
                          ("Quit", "quit")):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", lambda _, name=action: print(name, flush=True))
        menu.append(item)
    menu.show_all()
    indicator.set_menu(menu)
    indicator.set_status(indicator_module.IndicatorStatus.ACTIVE)

    def command(_source, condition):
        if condition & (GLib.IO_HUP | GLib.IO_ERR):
            Gtk.main_quit()
            return False
        line = sys.stdin.readline()
        if not line:
            Gtk.main_quit()
            return False
        indicator.set_label("Sharing" if line.strip() == "sharing" else "", "")
        return True

    GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP | GLib.IO_ERR, command)
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
