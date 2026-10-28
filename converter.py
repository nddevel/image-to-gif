"""Image -> GIF conversion logic. Contains no UI code."""

import os
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageSequence

# Optional: HEIC/HEIF (iPhone photos) and AVIF support.
try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    if hasattr(pillow_heif, "register_avif_opener"):
        try:
            pillow_heif.register_avif_opener()
        except Exception:
            pass
except ImportError:
    pass

# Optional: GdkPixbuf as a fallback loader for formats Pillow can't read (e.g. SVG).
try:
    import gi

    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
except (ImportError, ValueError):
    GdkPixbuf = None

# Every GIF frame uses palette index 255 as its transparent colour.
TRANSPARENT_INDEX = 255
MIN_FRAME_DELAY_MS = 20  # Browsers treat anything faster as 100 ms.


@dataclass
class Options:
    frame_delay_ms: int = 500
    loop_forever: bool = True
    max_size: int = 0  # 0 = keep original size
    dither: bool = True


class ConversionError(Exception):
    pass


def _to_rgba(frame):
    """Convert any Pillow mode (16-bit, float, CMYK, palette...) to RGBA."""
    if frame.mode in ("I;16", "I;16L", "I;16B", "I;16N"):
        frame = frame.convert("I")
    if frame.mode in ("I", "F"):
        low, high = frame.getextrema()
        if high > 255:
            frame = frame.point(lambda v: v * (255.0 / high))
        frame = frame.convert("L")
    if frame.mode == "RGBA":
        return frame.copy()
    try:
        return frame.convert("RGBA")
    except ValueError:
        return frame.convert("RGB").convert("RGBA")


def _load_with_pillow(path):
    """Return a list of (RGBA image, duration in ms or None)."""
    with Image.open(path) as im:
        n_frames = getattr(im, "n_frames", 1)
        if n_frames <= 1:
            # Respect camera rotation stored in EXIF (common for JPEG photos).
            image = ImageOps.exif_transpose(im)
            return [(_to_rgba(image), None)]

        frames = []
        for frame in ImageSequence.Iterator(im):
            duration = frame.info.get("duration")
            frames.append((_to_rgba(frame), int(duration) if duration else None))
        return frames


def _load_with_gdkpixbuf(path):
    pixbuf = GdkPixbuf.Pixbuf.new_from_file(path)
    pixbuf = pixbuf.apply_embedded_orientation() or pixbuf
    mode = "RGBA" if pixbuf.get_has_alpha() else "RGB"
    data = pixbuf.read_pixel_bytes().get_data()
    image = Image.frombuffer(
        mode,
        (pixbuf.get_width(), pixbuf.get_height()),
        data,
        "raw",
        mode,
        pixbuf.get_rowstride(),
        1,
    )
    return [(image.convert("RGBA"), None)]


def load_frames(path):
    """Load any supported image file as a list of (RGBA image, duration)."""
    pillow_error = None
    try:
        return _load_with_pillow(path)
    except Exception as e:
        pillow_error = e

    if GdkPixbuf is not None:
        try:
            return _load_with_gdkpixbuf(path)
        except Exception:
            pass

    raise ConversionError(f"Unsupported or damaged image ({pillow_error})")


def _resize(image, max_size):
    if max_size > 0 and max(image.size) > max_size:
        return ImageOps.contain(image, (max_size, max_size), Image.Resampling.LANCZOS)
    return image


def _fit_on_canvas(images):
    """GIF frames must all share one size: center each on a transparent canvas."""
    width = max(img.width for img in images)
    height = max(img.height for img in images)
    result = []
    for img in images:
        if img.size == (width, height):
            result.append(img)
            continue
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        canvas.paste(img, ((width - img.width) // 2, (height - img.height) // 2))
        result.append(canvas)
    return result


def _to_gif_frame(rgba, dither):
    """Reduce an RGBA image to a 255-colour palette + 1 transparent index."""
    dither_mode = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    frame = rgba.convert("RGB").quantize(
        colors=255, method=Image.Quantize.MEDIANCUT, dither=dither_mode
    )

    # Pad the palette to the full 256 entries so index 255 is always valid.
    palette = (frame.getpalette() or [])[: 255 * 3]
    palette += [0] * (768 - len(palette))
    frame.putpalette(palette)

    # GIF transparency is on/off only: pixels less than 50% opaque become transparent.
    transparent_mask = rgba.getchannel("A").point(lambda a: 255 if a < 128 else 0)
    frame.paste(TRANSPARENT_INDEX, mask=transparent_mask)
    frame.info["transparency"] = TRANSPARENT_INDEX
    return frame


def _save_gif(rgba_frames, durations, out_path, options):
    gif_frames = [_to_gif_frame(img, options.dither) for img in rgba_frames]
    first = gif_frames[0]

    if len(gif_frames) == 1:
        first.save(
            out_path,
            format="GIF",
            transparency=TRANSPARENT_INDEX,
            optimize=False,
        )
        return

    save_args = dict(
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=[max(MIN_FRAME_DELAY_MS, int(d)) for d in durations],
        disposal=2,  # clear each frame before drawing the next (needed for transparency)
        transparency=TRANSPARENT_INDEX,
        optimize=False,
    )
    if options.loop_forever:
        save_args["loop"] = 0
    first.save(out_path, **save_args)


def unique_path(path):
    """Return path, or 'name (1).gif', 'name (2).gif'... if it already exists."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"


def convert_single(path, out_dir, options):
    """Convert one image to its own GIF. Animated inputs keep their animation.

    Returns the path of the written GIF.
    """
    frames = load_frames(path)
    images = _fit_on_canvas([_resize(img, options.max_size) for img, _ in frames])
    durations = [d if d else options.frame_delay_ms for _, d in frames]

    stem = os.path.splitext(os.path.basename(path))[0]
    out_path = unique_path(os.path.join(out_dir or os.path.dirname(path), stem + ".gif"))
    _save_gif(images, durations, out_path, options)
    return out_path


def convert_combined(paths, out_path, options, progress=None):
    """Combine several images into one animated GIF (one image per frame).

    progress(index, path) is called before each input is loaded.
    Returns (out_path, failures) where failures is a list of (path, message).
    """
    images = []
    failures = []
    for i, path in enumerate(paths):
        if progress:
            progress(i, path)
        try:
            for img, _ in load_frames(path):
                images.append(_resize(img, options.max_size))
        except Exception as e:
            failures.append((path, str(e)))

    if not images:
        raise ConversionError("None of the images could be read")

    images = _fit_on_canvas(images)
    _save_gif(images, [options.frame_delay_ms] * len(images), out_path, options)
    return out_path, failures
