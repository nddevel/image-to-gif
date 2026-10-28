# Image to GIF

A simple GNOME app for turning images into GIFs. Built with GTK 4 and libadwaita.

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

## Requirements

- Python 3.10+
- GTK 4.12+ and libadwaita 1.5+
- PyGObject
- Pillow
- Optional: `pillow-heif` for HEIC/HEIF, librsvg for SVG

## Installation

First get the code:

```sh
git clone https://github.com/<your-username>/image-to-gif.git
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

1. Add images with the **+** button, or drag them into the window.
2. Pick an output mode: **One GIF per image** or **One animated GIF from all images**.
3. Adjust the settings if you want.
4. Click **Convert**. A notification appears with a **Show in Folder** button.

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
| `image_to_gif.py` | GTK 4 / libadwaita user interface |
| `converter.py` | Image loading and GIF encoding (no UI code) |
| `shell.nix` | Nix development environment with all dependencies |
| `run.sh` | Starts the app inside the Nix environment |
| `install-desktop-entry.sh` | Adds the app to the GNOME app grid |

## License

[MIT](LICENSE)
