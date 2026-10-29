# Image to GIF

A simple app for turning images into GIFs, for **Linux (GNOME)** and **Windows**.
The Linux version is built with GTK 4 and libadwaita. The Windows version has its own native window.

Drop in a PNG, JPG, WebP, HEIC, SVG or almost any other image and get a GIF back.
You can convert each image to its own GIF or combine many images into one animated GIF.

## Features

- **Reads almost any image format:** PNG, JPG/JPEG, WebP, BMP, TIFF, GIF, ICO, TGA,
  PPM/PGM/PBM, PCX, DDS, PSD, JPEG 2000, QOI, HEIC/HEIF (iPhone photos), AVIF, SVG,
  and anything else [Pillow](https://python-pillow.org/) or GdkPixbuf can open.
- **Two modes:**
  - *One GIF per image*: saved next to the original or in a folder you choose.
  - *One animated GIF*: a slideshow made from all selected images.
- **Keeps animation** from animated WebP, APNG and GIF files.
- **Keeps transparency** and rotates photos correctly using their EXIF data.
- **Settings:** frame duration, loop forever or play once, maximum size, dithering.
- **Easy to add images:** add button, <kbd>Ctrl</kbd>+<kbd>O</kbd>, drag and drop
  (files or whole folders), or *Open With* from the Files app.
- **Never overwrites files:** if `photo.gif` exists, it saves `photo (1).gif`.

## Windows

1. Go to the [**Releases**](https://github.com/nddevel/image-to-gif/releases/latest) page
   and download **`ImageToGif.exe`**.
2. Double-click it. You don't need to install anything.

The first time, Windows may show *"Windows protected your PC"*. That's because the app
isn't signed with a paid certificate. Click **More info → Run anyway**.

You can also drag images onto `ImageToGif.exe` itself, or right-click an image →
*Open with* → *Choose another app* → pick `ImageToGif.exe`.

> The Windows version supports every format above except SVG.

### Run the Windows version from source

Install [Python 3.10+](https://www.python.org/downloads/) (tick *Add python.exe to PATH*), then:

```bat
py -m pip install -r requirements-windows.txt
py image_to_gif_windows.py
```

## Linux requirements

- Python 3.10+
- GTK 4.12+ and libadwaita 1.5+
- PyGObject
- Pillow
- Optional: `pillow-heif` for HEIC/HEIF, librsvg for SVG

## Linux installation

First get the code:

```sh
git clone https://github.com/nddevel/image-to-gif.git
cd image-to-gif
```

### NixOS / Nix

Everything is listed in `shell.nix`. Download it all once:

```sh
nix-shell shell.nix --run true
```

Then start the app:

```sh
./run.sh
```

### Ubuntu / Debian

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-pil
python3 image_to_gif.py
```

### Fedora

```sh
sudo dnf install python3-gobject gtk4 libadwaita python3-pillow
python3 image_to_gif.py
```

### Arch Linux

```sh
sudo pacman -S python-gobject gtk4 libadwaita python-pillow
python3 image_to_gif.py
```

## Add it to the GNOME app grid (Nix)

```sh
./install-desktop-entry.sh
```

This adds *Image to GIF* to the app grid and to the *Open With* menu for images.
It only writes `~/.local/share/applications/io.github.imagetogif.ImageToGif.desktop`.
Delete that file to remove it.

## Usage

1. Add images with the **+** button (Linux) or **Add Images…** (Windows), or drag them into the window.
2. Pick an output mode: **One GIF per image** or **One animated GIF from all images**.
3. Adjust the settings if you want.
4. Click **Convert**. When it finishes, you can open the folder with the new GIFs.

You can also pass files on the command line:

```sh
python3 image_to_gif.py photo.jpg logo.png   # or ./run.sh photo.jpg logo.png on Nix
```

## Notes on the GIF format

GIF supports at most 256 colours per frame and only on/off transparency.
That means:

- Photos may look slightly grainy. Turning on **Dithering** (the default) gives smoother gradients.
- Semi-transparent edges become fully transparent or fully opaque.
- Large photos make large GIFs. Use **Maximum size** to scale them down.

## Project structure

| File | Purpose |
| --- | --- |
| `image_to_gif.py` | Linux/GNOME user interface (GTK 4 / libadwaita) |
| `image_to_gif_windows.py` | Windows user interface (Tkinter) |
| `converter.py` | Image loading and GIF encoding, shared by both versions |
| `requirements-windows.txt` | Python packages for the Windows version |
| `.github/workflows/windows.yml` | Builds, tests and publishes `ImageToGif.exe` |
| `shell.nix` | Nix development environment with all dependencies |
| `run.sh` | Starts the app inside the Nix environment |
| `install-desktop-entry.sh` | Adds the app to the GNOME app grid |

## Making a Windows release

Every push to `main` builds and tests `ImageToGif.exe` on GitHub
(*Actions* tab → latest run → *Artifacts*). To publish it on the Releases page, push a version tag:

```sh
git tag v1.0.0
git push origin v1.0.0
```

## License

[MIT](LICENSE)
