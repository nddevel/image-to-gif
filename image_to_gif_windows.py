#!/usr/bin/env python3
"""Image to GIF for Windows: a Tkinter front end for converter.py.

The GNOME version is image_to_gif.py. Both share converter.py, so they
produce identical GIFs.
"""

import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

import converter

# Optional: drag and drop support.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

APP_NAME = "Image to GIF"
VERSION = "1.0"

MODE_SEPARATE = 0
MODE_COMBINED = 1

SAME_FOLDER_TEXT = "Same folder as each image"
MAX_FRAME_DELAY_MS = 60000
MAX_SIZE_LIMIT = 10000
SELF_TEST_TIMEOUT_MS = 180000

FILETYPES = [
    ("Images", " ".join("*." + s for s in converter.IMAGE_SUFFIXES)),
    ("All files", "*.*"),
]


def make_root():
    """Create the main Tk window, with drag and drop if tkinterdnd2 works."""
    if TkinterDnD is not None:
        try:
            return TkinterDnD.Tk(), True
        except Exception:
            pass
    return tk.Tk(), False


def open_folder(path):
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError:
        pass


def set_enabled(widget, enabled):
    widget.state(["!disabled"] if enabled else ["disabled"])


class ImageToGifApp:
    def __init__(self, root, dnd_enabled, interactive=True):
        self.root = root
        self.dnd_enabled = dnd_enabled
        self.interactive = interactive  # False during the automated self-test
        self.paths = []  # input files, in order
        self._path_keys = set()  # normalised paths, to skip duplicates
        self.output_dir = None  # None = next to each source image
        self.busy = False
        self.events = queue.Queue()  # messages from the worker thread
        self.last_result = None  # (outputs, failures) of the last conversion
        self.errors = []  # unexpected exceptions (self-test only)

        root.title(APP_NAME)
        root.minsize(560, 600)
        root.report_callback_exception = self._report_exception
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.mode = tk.IntVar(value=MODE_SEPARATE)
        self.delay = tk.StringVar(value="500")
        self.max_size = tk.StringVar(value="0")
        self.loop_forever = tk.BooleanVar(value=True)
        self.dither = tk.BooleanVar(value=True)
        self.output_text = tk.StringVar(value=SAME_FOLDER_TEXT)
        self.status = tk.StringVar()

        self._build_ui()
        self._setup_drag_and_drop()
        root.bind("<Control-o>", lambda _e: self.choose_images())
        self._update_state()

    # ---------- UI construction ----------

    def _build_ui(self):
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(main)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.add_button = ttk.Button(toolbar, text="Add Images…", command=self.choose_images)
        self.add_folder_button = ttk.Button(toolbar, text="Add Folder…",
                                            command=self.choose_folder_of_images)
        self.remove_button = ttk.Button(toolbar, text="Remove", command=self.remove_selected)
        self.clear_button = ttk.Button(toolbar, text="Clear All", command=self.clear_images)
        for button in (self.add_button, self.add_folder_button, self.remove_button, self.clear_button):
            button.pack(side="left", padx=(0, 6))

        list_frame = ttk.Frame(main)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(list_frame, selectmode="extended", height=10, activestyle="none")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.bind("<Delete>", lambda _e: self.remove_selected())
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._update_state())

        self.hint = ttk.Label(main, foreground="gray")
        self.hint.grid(row=2, column=0, sticky="w", pady=(4, 10))

        settings = ttk.LabelFrame(main, text="Settings", padding=10)
        settings.grid(row=3, column=0, sticky="ew")
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Output:").grid(row=0, column=0, sticky="nw", padx=(0, 10))
        modes = ttk.Frame(settings)
        modes.grid(row=0, column=1, columnspan=3, sticky="w")
        self.separate_radio = ttk.Radiobutton(modes, text="One GIF per image", variable=self.mode,
                                              value=MODE_SEPARATE, command=self._update_state)
        self.combined_radio = ttk.Radiobutton(modes, text="One animated GIF from all images",
                                              variable=self.mode, value=MODE_COMBINED,
                                              command=self._update_state)
        self.separate_radio.pack(anchor="w")
        self.combined_radio.pack(anchor="w")

        ttk.Label(settings, text="Frame duration (ms):").grid(row=1, column=0, sticky="w",
                                                              padx=(0, 10), pady=(10, 0))
        self.delay_spin = ttk.Spinbox(settings, from_=converter.MIN_FRAME_DELAY_MS,
                                      to=MAX_FRAME_DELAY_MS, increment=10, width=8,
                                      textvariable=self.delay)
        self.delay_spin.grid(row=1, column=1, sticky="w", pady=(10, 0))
        self.delay_hint = ttk.Label(settings, foreground="gray")
        self.delay_hint.grid(row=1, column=2, columnspan=2, sticky="w", padx=(8, 0), pady=(10, 0))

        ttk.Label(settings, text="Maximum size (px):").grid(row=2, column=0, sticky="w",
                                                            padx=(0, 10), pady=(6, 0))
        self.size_spin = ttk.Spinbox(settings, from_=0, to=MAX_SIZE_LIMIT, increment=50, width=8,
                                     textvariable=self.max_size)
        self.size_spin.grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(settings, text="Longest side; 0 = keep original size",
                  foreground="gray").grid(row=2, column=2, columnspan=2, sticky="w",
                                          padx=(8, 0), pady=(6, 0))

        self.loop_check = ttk.Checkbutton(settings, text="Loop forever (otherwise plays once)",
                                          variable=self.loop_forever)
        self.loop_check.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        self.dither_check = ttk.Checkbutton(
            settings, text="Dithering (smoother colours; GIF supports only 256)",
            variable=self.dither)
        self.dither_check.grid(row=4, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.save_label = ttk.Label(settings, text="Save to:")
        self.save_label.grid(row=5, column=0, sticky="w", padx=(0, 10), pady=(10, 0))
        self.output_entry = ttk.Entry(settings, textvariable=self.output_text, state="readonly")
        self.output_entry.grid(row=5, column=1, sticky="ew", pady=(10, 0))
        self.browse_button = ttk.Button(settings, text="Browse…", command=self.choose_output_folder)
        self.browse_button.grid(row=5, column=2, padx=(6, 0), pady=(10, 0))
        self.reset_button = ttk.Button(settings, text="Reset",
                                       command=lambda: self._set_output_dir(None))
        self.reset_button.grid(row=5, column=3, padx=(6, 0), pady=(10, 0))

        bottom = ttk.Frame(main)
        bottom.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(bottom, mode="determinate", maximum=1.0)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.convert_button = ttk.Button(bottom, text="Convert to GIF", command=self.start_conversion)
        self.convert_button.grid(row=0, column=1)
        ttk.Label(bottom, textvariable=self.status).grid(row=1, column=0, columnspan=2,
                                                         sticky="w", pady=(4, 0))

    def _setup_drag_and_drop(self):
        if not self.dnd_enabled:
            return
        try:
            for widget in (self.root, self.listbox):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
        except Exception:
            self.dnd_enabled = False

    # ---------- State ----------

    def _update_state(self):
        has_images = bool(self.paths)
        idle = not self.busy
        combined = self.mode.get() == MODE_COMBINED

        self.listbox.configure(state="normal" if idle else "disabled")
        set_enabled(self.remove_button, idle and bool(self.listbox.curselection()))
        set_enabled(self.clear_button, idle and has_images)
        set_enabled(self.convert_button, idle and has_images)
        set_enabled(self.reset_button, idle and self.output_dir is not None)
        for widget in (self.add_button, self.add_folder_button, self.separate_radio,
                       self.combined_radio, self.delay_spin, self.size_spin, self.loop_check,
                       self.dither_check, self.browse_button):
            set_enabled(widget, idle)

        for widget in (self.save_label, self.output_entry, self.browse_button, self.reset_button):
            if combined:
                widget.grid_remove()
            else:
                widget.grid()

        self.delay_hint.configure(text="How long each image is shown" if combined
                                  else "Used for multi-page images without timing")
        if combined:
            self.convert_button.configure(text="Create Animated GIF")
        elif len(self.paths) > 1:
            self.convert_button.configure(text=f"Convert {len(self.paths)} Images to GIF")
        else:
            self.convert_button.configure(text="Convert to GIF")

        drop_text = "Drag and drop images or folders here, or use Add Images."
        if not self.dnd_enabled:
            drop_text = "Use Add Images or Add Folder to choose images."
        self.hint.configure(text=f"{len(self.paths)} image(s) selected. {drop_text}"
                            if has_images else drop_text)

    def _set_output_dir(self, path):
        self.output_dir = path
        self.output_text.set(path if path else SAME_FOLDER_TEXT)
        self._update_state()

    def _read_options(self):
        try:
            delay = int(float(self.delay.get()))
            max_size = int(float(self.max_size.get()))
        except ValueError:
            raise ValueError("Frame duration and maximum size must be numbers.") from None
        delay = min(max(delay, converter.MIN_FRAME_DELAY_MS), MAX_FRAME_DELAY_MS)
        max_size = min(max(max_size, 0), MAX_SIZE_LIMIT)
        self.delay.set(str(delay))
        self.max_size.set(str(max_size))
        return converter.Options(
            frame_delay_ms=delay,
            loop_forever=self.loop_forever.get(),
            max_size=max_size,
            dither=self.dither.get(),
        )

    # ---------- Image list ----------

    def add_paths(self, paths):
        """Add image files and/or folders of images. Returns how many were added."""
        if self.busy:
            return 0
        added = 0
        for path in paths:
            path = os.path.abspath(path)
            if os.path.isdir(path):
                try:
                    names = sorted(os.listdir(path), key=str.lower)
                except OSError:
                    continue
                candidates = [os.path.join(path, n) for n in names]
                candidates = [p for p in candidates
                              if os.path.isfile(p) and converter.is_image_name(p)]
            elif os.path.isfile(path):
                candidates = [path]
            else:
                candidates = []
            for candidate in candidates:
                key = os.path.normcase(candidate)
                if key in self._path_keys:
                    continue
                self._path_keys.add(key)
                self.paths.append(candidate)
                self.listbox.insert("end", candidate)
                added += 1
        if paths:
            self.status.set(f"Added {added} image(s)" if added else "No new images were added")
        self._update_state()
        return added

    def remove_selected(self):
        if self.busy:
            return
        for index in reversed(self.listbox.curselection()):
            self._path_keys.discard(os.path.normcase(self.paths[index]))
            del self.paths[index]
            self.listbox.delete(index)
        self._update_state()

    def clear_images(self):
        if self.busy:
            return
        self.paths.clear()
        self._path_keys.clear()
        self.listbox.delete(0, "end")
        self._update_state()

    def _on_drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))
        return event.action

    # ---------- Dialogs ----------

    def choose_images(self):
        if self.busy:
            return
        files = filedialog.askopenfilenames(parent=self.root, title="Choose Images",
                                            filetypes=FILETYPES)
        if isinstance(files, str):
            files = self.root.tk.splitlist(files)
        if files:
            self.add_paths(files)

    def choose_folder_of_images(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(parent=self.root, title="Choose a Folder of Images")
        if folder:
            self.add_paths([folder])

    def choose_output_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Choose Where to Save GIFs")
        if folder:
            self._set_output_dir(os.path.abspath(folder))

    def _show_error(self, title, message):
        if self.interactive:
            messagebox.showerror(title, message, parent=self.root)
        else:
            self.errors.append(f"{title}: {message}")

    def _report_exception(self, exc_type, exc_value, exc_tb):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self._show_error(f"{APP_NAME}: unexpected error", details[-3000:])

    def _on_close(self):
        if self.busy and self.interactive and not messagebox.askyesno(
                APP_NAME, "A conversion is still running. Quit anyway?", parent=self.root):
            return
        self.root.destroy()

    # ---------- Conversion ----------

    def start_conversion(self, out_path=None):
        """Start converting in a background thread.

        out_path is only used in "one animated GIF" mode; if None, a save dialog asks for it.
        """
        if self.busy or not self.paths:
            return
        try:
            options = self._read_options()
        except ValueError as e:
            self._show_error("Invalid setting", str(e))
            return

        paths = list(self.paths)
        if self.mode.get() == MODE_COMBINED:
            if out_path is None:
                out_path = filedialog.asksaveasfilename(
                    parent=self.root, title="Save Animated GIF", defaultextension=".gif",
                    filetypes=[("GIF image", "*.gif")], initialfile="animation.gif",
                    initialdir=os.path.dirname(paths[0]))
                if not out_path:
                    return
            if not out_path.lower().endswith(".gif"):
                out_path += ".gif"
            worker, args = self._combined_worker, (paths, out_path, options)
        else:
            worker, args = self._separate_worker, (paths, self.output_dir, options)

        self.busy = True
        self.last_result = None
        self.progress["value"] = 0
        self.status.set("Starting…")
        self._update_state()
        threading.Thread(target=worker, args=args, daemon=True).start()
        self.root.after(100, self._poll_events)

    def _separate_worker(self, paths, out_dir, options):
        outputs, failures = [], []
        for i, path in enumerate(paths):
            self.events.put(("progress", i, len(paths), path))
            try:
                outputs.append(converter.convert_single(path, out_dir, options))
            except Exception as e:
                failures.append((path, str(e)))
        self.events.put(("done", outputs, failures))

    def _combined_worker(self, paths, out_path, options):
        try:
            out, failures = converter.convert_combined(
                paths, out_path, options,
                progress=lambda i, p: self.events.put(("progress", i, len(paths), p)),
            )
            outputs = [out]
        except Exception as e:
            outputs, failures = [], [("All images", str(e))]
        self.events.put(("done", outputs, failures))

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, index, total, path = event
                    self.progress["value"] = index / total
                    self.status.set(f"{index + 1} of {total}: {os.path.basename(path)}")
                elif event[0] == "done":
                    self._on_finished(event[1], event[2])
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_finished(self, outputs, failures):
        self.busy = False
        self.last_result = (outputs, failures)
        self.progress["value"] = 1.0 if outputs else 0
        if len(outputs) == 1:
            summary = f"Saved {os.path.basename(outputs[0])}"
        elif outputs:
            summary = f"Created {len(outputs)} GIFs"
        else:
            summary = "Nothing was converted"
        self.status.set(summary)
        self._update_state()

        if not self.interactive:
            return
        if failures:
            lines = [f"• {os.path.basename(p)}: {msg}" for p, msg in failures[:15]]
            if len(failures) > 15:
                lines.append(f"…and {len(failures) - 15} more")
            messagebox.showwarning(
                APP_NAME, f"{len(failures)} image(s) could not be converted:\n\n" + "\n".join(lines),
                parent=self.root)
        if outputs and messagebox.askyesno(APP_NAME, f"{summary}.\n\nOpen the folder?",
                                           parent=self.root):
            open_folder(os.path.dirname(outputs[0]))


# ---------- Automated self-test (used by the Windows build on GitHub) ----------

def _make_test_images(folder):
    from PIL import Image, ImageDraw

    paths = []

    def add(name, image, **save_args):
        path = os.path.join(folder, name)
        image.save(path, **save_args)
        paths.append(path)

    transparent = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(transparent).ellipse((10, 10, 110, 110), fill=(0, 120, 255, 255))
    add("transparent.png", transparent)
    add("photo.jpg", Image.new("RGB", (160, 90), (200, 30, 30)))
    add("bitmap.bmp", Image.new("RGB", (70, 70), (30, 160, 30)))
    add("scan.tiff", Image.new("RGB", (90, 60), (200, 200, 30)))
    frames = [Image.new("RGBA", (80, 60), c) for c in ((255, 0, 255, 255), (0, 255, 255, 255))]
    add("animated.webp", frames[0], save_all=True, append_images=frames[1:],
        duration=[100, 200], loop=0, lossless=True)
    if "pillow_heif" in sys.modules:
        add("iphone.heic", Image.new("RGB", (64, 48), (255, 140, 0)))
    return paths


def _gif_frames(path):
    from PIL import Image

    with Image.open(path) as image:
        return getattr(image, "n_frames", 1) if image.format == "GIF" else 0


def run_self_test(log_path):
    """Drive the real window and conversion code without any dialogs. Returns an exit code."""
    lines = []
    failed = []

    def log(message):
        lines.append(message)
        print(message)

    def check(condition, message):
        log(("PASS " if condition else "FAIL ") + message)
        if not condition:
            failed.append(message)

    root, dnd = make_root()
    root.withdraw()
    app = ImageToGifApp(root, dnd, interactive=False)
    log(f"python={sys.version.split()[0]} frozen={getattr(sys, 'frozen', False)}")
    log(f"dnd={'yes' if app.dnd_enabled else 'no'} "
        f"heif={'yes' if 'pillow_heif' in sys.modules else 'no'}")

    workdir = tempfile.mkdtemp(prefix="image-to-gif-selftest-")
    out_dir = os.path.join(workdir, "out")
    os.makedirs(out_dir)

    def steps():
        inputs = _make_test_images(workdir)
        added = app.add_paths(inputs)
        check(added == len(inputs), f"added {added} of {len(inputs)} images")
        check(app.add_paths(inputs) == 0, "duplicates are skipped")

        app._set_output_dir(out_dir)
        app.start_conversion()
        yield
        outputs, failures = app.last_result or ([], [("no result", "")])
        check(len(outputs) == len(inputs) and not failures,
              f"one GIF per image: {len(outputs)} created, failures={failures}")
        for path in outputs:
            check(_gif_frames(path) >= 1, f"valid GIF: {os.path.basename(path)}")
        webp_gif = os.path.join(out_dir, "animated.gif")
        check(os.path.exists(webp_gif) and _gif_frames(webp_gif) == 2,
              "animated WebP keeps its 2 frames")

        app.mode.set(MODE_COMBINED)
        app._update_state()
        combined = os.path.join(workdir, "combined")  # ".gif" is added automatically
        app.start_conversion(out_path=combined)
        yield
        outputs, failures = app.last_result or ([], [("no result", "")])
        check(outputs == [combined + ".gif"] and not failures,
              f"animated GIF created: {outputs}, failures={failures}")
        if outputs:
            frames = _gif_frames(outputs[0])
            check(frames >= len(inputs), f"animated GIF has {frames} frames")

    sequence = steps()
    done = []

    def finish():
        if done:
            return
        done.append(True)
        for error in app.errors:
            check(False, error)
        log("RESULT: " + ("FAILED" if failed else "ALL PASSED"))
        if log_path:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        root.destroy()

    def advance():
        if done:
            return
        if app.busy:
            root.after(100, advance)
            return
        try:
            next(sequence)
        except StopIteration:
            finish()
            return
        except Exception:
            check(False, traceback.format_exc())
            finish()
            return
        root.after(100, advance)

    def timeout():
        if not done:
            check(False, "self-test timed out")
            finish()

    root.after(200, advance)
    root.after(SELF_TEST_TIMEOUT_MS, timeout)
    root.mainloop()
    return 1 if failed else 0


def main():
    if sys.platform == "win32":
        # Sharp (not blurry) text on high-DPI screens.
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

    args = sys.argv[1:]
    if args[:1] == ["--self-test"]:
        return run_self_test(args[1] if len(args) > 1 else None)

    root, dnd = make_root()
    app = ImageToGifApp(root, dnd)
    # Files dropped onto ImageToGif.exe (or opened with it) arrive as arguments.
    files = [a for a in args if not a.startswith("--")]
    if files:
        app.add_paths(files)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
