# Everything Image to GIF needs. Download it all once with:
#   nix-shell shell.nix --run true
{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  nativeBuildInputs = [ pkgs.gobject-introspection ];
  buildInputs = [
    pkgs.gtk4
    pkgs.libadwaita
    pkgs.gdk-pixbuf
    pkgs.librsvg # SVG support
    (pkgs.python3.withPackages (ps: [
      ps.pygobject3
      ps.pillow
      ps.pillow-heif # HEIC/HEIF (iPhone photos) support
    ]))
  ];
}
