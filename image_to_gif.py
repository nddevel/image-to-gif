#!/usr/bin/env python3
"""Image to GIF: a small GNOME app that converts images (PNG, JPG, WebP, ...) to GIF."""

import os
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

import converter  # noqa: E402

APP_ID = "io.github.imagetogif.ImageToGif"
APP_NAME = "Image to GIF"
VERSION = "1.0"

MODE_SEPARATE = 0
MODE_COMBINED = 1

IMAGE_SUFFIXES = [
    "png", "jpg", "jpeg", "jpe", "jfif", "gif", "bmp", "dib", "webp", "tif", "tiff",
    "ico", "icns", "tga", "ppm", "pgm", "pbm", "pnm", "pcx", "dds", "psd", "jp2",
    "j2k", "heic", "heif", "avif", "svg", "svgz", "xbm", "xpm", "qoi", "jxl",
]


class ImageToGifWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(560, 720)

        self.paths = []  # input files, in order
        self.output_dir = None  # None = next to each source image
        self.busy = False

        self.toasts = Adw.ToastOverlay()
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(self._build_header())
        toolbar_view.set_content(self._build_content())
        toolbar_view.add_bottom_bar(self._build_bottom_bar())
        self.toasts.set_child(toolbar_view)
        self.set_content(self.toasts)

        drop = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.add_controller(drop)

        self._update_state()

    # ---------- UI construction ----------

    def _build_header(self):
        header = Adw.HeaderBar()

        add_button = Gtk.Button(icon_name="list-add-symbolic", tooltip_text="Add Images (Ctrl+O)")
        add_button.set_action_name("win.add-images")
        header.pack_start(add_button)

        self.clear_button = Gtk.Button(icon_name="edit-clear-all-symbolic", tooltip_text="Remove All Images")
        self.clear_button.connect("clicked", lambda *_: self.clear_images())
        header.pack_start(self.clear_button)

        menu = Gio.Menu()
        menu.append("About Image to GIF", "app.about")
        menu.append("Quit", "app.quit")
        header.pack_end(Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu,
                                       tooltip_text="Main Menu"))

        action = Gio.SimpleAction.new("add-images", None)
        action.connect("activate", lambda *_: self.open_file_dialog())
        self.add_action(action)
        return header

    def _build_content(self):
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)

        # Empty state
        open_button = Gtk.Button(label="Choose Images…", halign=Gtk.Align.CENTER)
        open_button.add_css_class("pill")
        open_button.add_css_class("suggested-action")
        open_button.set_action_name("win.add-images")
        empty = Adw.StatusPage(
            icon_name="image-x-generic-symbolic",
            title="Add Images",
            description="Drag and drop images here, or choose them from your files.\n"
                        "PNG, JPG, WebP, BMP, TIFF, HEIC, AVIF, SVG and more are supported.",
            child=open_button,
        )
        self.stack.add_named(empty, "empty")

        # Image list + settings
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                      margin_top=24, margin_bottom=24, margin_start=12, margin_end=12)

        self.images_group = Adw.PreferencesGroup(title="Images")
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.images_group.add(self.listbox)
        box.append(self.images_group)

        settings = Adw.PreferencesGroup(title="Settings")

        self.mode_row = Adw.ComboRow(
            title="Output",
            model=Gtk.StringList.new(["One GIF per image", "One animated GIF from all images"]),
        )
        self.mode_row.connect("notify::selected", lambda *_: self._update_state())
        settings.add(self.mode_row)

        self.delay_row = Adw.SpinRow.new_with_range(20, 60000, 10)
        self.delay_row.set_title("Frame duration")
        self.delay_row.set_subtitle("Milliseconds each image is shown")
        self.delay_row.set_value(500)
        settings.add(self.delay_row)

        self.loop_row = Adw.SwitchRow(title="Loop forever", subtitle="Otherwise the animation plays once",
                                      active=True)
        settings.add(self.loop_row)

        self.size_row = Adw.SpinRow.new_with_range(0, 10000, 50)
        self.size_row.set_title("Maximum size")
        self.size_row.set_subtitle("Longest side in pixels (0 = keep original size)")
        self.size_row.set_value(0)
        settings.add(self.size_row)

        self.dither_row = Adw.SwitchRow(
            title="Dithering",
            subtitle="Smoother colour gradients (GIF supports only 256 colours)",
            active=True,
        )
        settings.add(self.dither_row)

        self.folder_row = Adw.ActionRow(title="Save to", subtitle="Same folder as each image")
        folder_button = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                                   tooltip_text="Choose Folder")
        folder_button.add_css_class("flat")
        folder_button.connect("clicked", lambda *_: self.choose_output_folder())
        self.folder_reset_button = Gtk.Button(icon_name="edit-undo-symbolic", valign=Gtk.Align.CENTER,
                                              tooltip_text="Use Same Folder as Each Image")
        self.folder_reset_button.add_css_class("flat")
        self.folder_reset_button.connect("clicked", lambda *_: self._set_output_dir(None))
        self.folder_row.add_suffix(self.folder_reset_button)
        self.folder_row.add_suffix(folder_button)
        self.folder_row.set_activatable_widget(folder_button)
        settings.add(self.folder_row)

        box.append(settings)

        clamp = Adw.Clamp(maximum_size=600, child=box)
        scrolled = Gtk.ScrolledWindow(child=clamp, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.stack.add_named(scrolled, "list")
        self.settings_box = box
        return self.stack

    def _build_bottom_bar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        self.progress = Gtk.ProgressBar(show_text=True, visible=False)
        bar.append(self.progress)
        self.convert_button = Gtk.Button(label="Convert to GIF", halign=Gtk.Align.CENTER)
        self.convert_button.add_css_class("pill")
        self.convert_button.add_css_class("suggested-action")
        self.convert_button.connect("clicked", lambda *_: self.start_conversion())
        bar.append(self.convert_button)
        return bar

    # ---------- State ----------

    def _mode(self):
        return self.mode_row.get_selected()

    def _update_state(self):
        has_images = bool(self.paths)
        self.stack.set_visible_child_name("list" if has_images else "empty")
        self.images_group.set_description(f"{len(self.paths)} selected" if has_images else None)

        combined = self._mode() == MODE_COMBINED
        self.folder_row.set_visible(not combined)
        self.folder_reset_button.set_visible(self.output_dir is not None)
        self.delay_row.set_subtitle(
            "Milliseconds each image is shown" if combined
            else "Used for multi-page images without their own timing"
        )

        idle = not self.busy
        self.convert_button.set_sensitive(has_images and idle)
        self.clear_button.set_sensitive(has_images and idle)
        self.settings_box.set_sensitive(idle)
        self.lookup_action("add-images").set_enabled(idle)
        if combined:
            self.convert_button.set_label("Create Animated GIF")
        else:
            self.convert_button.set_label("Convert to GIF" if len(self.paths) <= 1
                                          else f"Convert {len(self.paths)} Images to GIF")

    def _set_output_dir(self, path):
        self.output_dir = path
        self.folder_row.set_subtitle(path if path else "Same folder as each image")
        self._update_state()

    def _options(self):
        return converter.Options(
            frame_delay_ms=int(self.delay_row.get_value()),
            loop_forever=self.loop_row.get_active(),
            max_size=int(self.size_row.get_value()),
            dither=self.dither_row.get_active(),
        )

    # ---------- Image list ----------

    def add_files(self, files):
        added = 0
        for f in files:
            path = f.get_path()
            if path is None or path in self.paths:
                continue
            if os.path.isdir(path):
                for name in sorted(os.listdir(path)):
                    child = os.path.join(path, name)
                    if (os.path.isfile(child) and child not in self.paths
                            and os.path.splitext(name)[1].lower().lstrip(".") in IMAGE_SUFFIXES):
                        self._add_row(child)
                        added += 1
            elif os.path.isfile(path):
                self._add_row(path)
                added += 1
        if added == 0 and files:
            self.toasts.add_toast(Adw.Toast(title="No new images were added"))
        self._update_state()

    def _add_row(self, path):
        self.paths.append(path)
        row = Adw.ActionRow(title=GLib.markup_escape_text(os.path.basename(path)),
                            subtitle=GLib.markup_escape_text(os.path.dirname(path)))
        row.add_prefix(Gtk.Image(icon_name="image-x-generic-symbolic"))
        remove = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                            tooltip_text="Remove")
        remove.add_css_class("flat")
        remove.connect("clicked", self._on_remove_clicked, row, path)
        row.add_suffix(remove)
        self.listbox.append(row)

    def _on_remove_clicked(self, _button, row, path):
        if self.busy:
            return
        self.paths.remove(path)
        self.listbox.remove(row)
        self._update_state()

    def clear_images(self):
        self.paths.clear()
        self.listbox.remove_all()
        self._update_state()

    def _on_drop(self, _target, value, _x, _y):
        if self.busy:
            return False
        self.add_files(value.get_files())
        return True

    # ---------- Dialogs ----------

    def open_file_dialog(self):
        image_filter = Gtk.FileFilter(name="Images")
        image_filter.add_mime_type("image/*")
        for suffix in IMAGE_SUFFIXES:
            image_filter.add_suffix(suffix)
        all_filter = Gtk.FileFilter(name="All Files")
        all_filter.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        filters.append(all_filter)

        dialog = Gtk.FileDialog(title="Choose Images", filters=filters, default_filter=image_filter)
        dialog.open_multiple(self, None, self._on_files_chosen)

    def _on_files_chosen(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return  # cancelled
        self.add_files([files.get_item(i) for i in range(files.get_n_items())])

    def choose_output_folder(self):
        dialog = Gtk.FileDialog(title="Choose Where to Save GIFs")
        dialog.select_folder(self, None, self._on_folder_chosen)

    def _on_folder_chosen(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder is not None and folder.get_path():
            self._set_output_dir(folder.get_path())

    # ---------- Conversion ----------

    def start_conversion(self):
        if self.busy or not self.paths:
            return
        if self._mode() == MODE_COMBINED:
            dialog = Gtk.FileDialog(title="Save Animated GIF", initial_name="animation.gif")
            dialog.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.paths[0])))
            dialog.save(self, None, self._on_save_path_chosen)
        else:
            self._run_in_thread(self._convert_separate_worker,
                                list(self.paths), self.output_dir, self._options())

    def _on_save_path_chosen(self, dialog, result):
        try:
            file = dialog.save_finish(result)
        except GLib.Error:
            return
        if file is None or not file.get_path():
            return
        out_path = file.get_path()
        if not out_path.lower().endswith(".gif"):
            out_path += ".gif"
        self._run_in_thread(self._convert_combined_worker, list(self.paths), out_path, self._options())

    def _run_in_thread(self, worker, *args):
        self.busy = True
        self.progress.set_fraction(0)
        self.progress.set_text("Starting…")
        self.progress.set_visible(True)
        self._update_state()
        threading.Thread(target=worker, args=args, daemon=True).start()

    def _report_progress(self, index, total, path):
        GLib.idle_add(self._set_progress, index / total,
                      f"{index + 1} of {total}: {os.path.basename(path)}")

    def _set_progress(self, fraction, text):
        self.progress.set_fraction(fraction)
        self.progress.set_text(text)
        return GLib.SOURCE_REMOVE

    def _convert_separate_worker(self, paths, out_dir, options):
        outputs, failures = [], []
        for i, path in enumerate(paths):
            self._report_progress(i, len(paths), path)
            try:
                outputs.append(converter.convert_single(path, out_dir, options))
            except Exception as e:
                failures.append((path, str(e)))
        GLib.idle_add(self._on_finished, outputs, failures)

    def _convert_combined_worker(self, paths, out_path, options):
        try:
            out, failures = converter.convert_combined(
                paths, out_path, options,
                progress=lambda i, p: self._report_progress(i, len(paths), p),
            )
            outputs = [out]
        except Exception as e:
            outputs, failures = [], [("All images", str(e))]
        GLib.idle_add(self._on_finished, outputs, failures)

    def _on_finished(self, outputs, failures):
        self.busy = False
        self.progress.set_visible(False)
        self._update_state()

        if outputs:
            title = (f"Saved {os.path.basename(outputs[0])}" if len(outputs) == 1
                     else f"Created {len(outputs)} GIFs")
            toast = Adw.Toast(title=GLib.markup_escape_text(title), button_label="Show in Folder",
                              timeout=6)
            toast.connect("button-clicked", lambda *_: self._show_in_folder(outputs[0]))
            self.toasts.add_toast(toast)

        if failures:
            body = "\n".join(f"• {os.path.basename(p)}: {msg}" for p, msg in failures)
            alert = Adw.AlertDialog(
                heading=f"{len(failures)} image(s) could not be converted",
                body=body,
            )
            alert.add_response("ok", "OK")
            alert.present(self)
        return GLib.SOURCE_REMOVE

    def _show_in_folder(self, path):
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(path))
        launcher.open_containing_folder(self, None, self._on_launch_done)

    @staticmethod
    def _on_launch_done(launcher, result):
        try:
            launcher.open_containing_folder_finish(result)
        except GLib.Error:
            pass


class ImageToGifApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        GLib.set_application_name(APP_NAME)
        self._add_action("about", self._on_about)
        self._add_action("quit", lambda *_: self.quit())
        self.set_accels_for_action("app.quit", ["<Control>q"])
        self.set_accels_for_action("win.add-images", ["<Control>o"])

    def _add_action(self, name, callback):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def _get_window(self):
        window = self.get_active_window()
        if window is None:
            window = ImageToGifWindow(self)
        return window

    def do_activate(self):
        self._get_window().present()

    def do_open(self, files, n_files, hint):
        window = self._get_window()
        window.present()
        if not window.busy:
            window.add_files(files)

    def _on_about(self, *_):
        about = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon="image-x-generic",
            version=VERSION,
            comments="Convert PNG, JPG, WebP, HEIC, SVG and other images to GIF.",
            license_type=Gtk.License.MIT_X11,
        )
        about.present(self.get_active_window())


def main():
    return ImageToGifApp().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
