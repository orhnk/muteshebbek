# muteshebbek

Bitmap-Font-Sammlung als Nix-Flake: 60+ pixel-perfekte Fonts plus ein
gemergter Font **Muteshebbek** – ein Strike pro px-Größe, 7–100px, als OTB
(mit echten Bitmap-Strikes) **und** TTF (mit getracten Outlines) für Apps, die
keine Bitmaps rendern können.

## Idee

Bitmap-Fonts sind nur in ihren nativen Größen wirklich scharf. Muteshebbek
mischt die Sammlung deshalb zu **einem** Font: Für jede Zielgröße gewinnt per
Priority-Liste genau ein Font; Größen ohne passenden Kandidaten werden per
integer-Faktor hochskaliert, letzte Lücken füllt ein 1-bit gerasterter
CozetteVector (Filler). So deckt der Font jede Größe von 7 bis 100px ab,
wahlweise pixel-perfect nativ oder ganzzahlig skaliert.

## Benutzen

In einer NixOS-Konfiguration:

```nix
{
  inputs.muteshebbek.url = "github:orhnk/muteshebbek";

  # ...
  fonts.packages = [
    inputs.muteshebbek.packages.${pkgs.stdenv.hostPlatform.system}.merged
  ];
  fonts.fontconfig.defaultFonts.monospace = [ "Muteshebbek" ];
}
```

Direkt bauen:

```sh
nix build .#merged -o result-merged      # Muteshebbek.otb + Muteshebbek.ttf
nix build .#all                          # alle Einzelfonts (default)
```

## Der Merge

Die Merge-Konfiguration steht in `flake.nix` (`mergeCfg`, `priority`,
`upscaleForced`) und ist die einzige Quelle der Wahrheit; die Python-Tools
bekommen daraus generierte JSONs.

- `priority` – Reihenfolge entscheidet pro px. Aufgelistete Fonts dürfen
  gewinnen und werden skaliert; auskommentierte Fonts landen trotzdem in `all`,
  aber nicht im Merge.
- `size_select` – Größen pro Font einschränken, Format `"font:size=9,12,13"`:
  der Font gewinnt dann nur bei diesen Größen nativ und wird nur aus ihnen
  hochskaliert; seine übrigen echten Größen bleiben in `all`, aber nicht im
  Merge. Die Größen müssen zu den echten Headern passen (Fehler sonst).
- `upscale_scope` / `--force` – welche Fonts über ihre nativen Größen hinaus
  per ganzzahligem Faktor multipliziert werden.
- `native_beats_scaled` – native Strikes schlagen skalierte; erst innerhalb
  derselben Kategorie entscheidet die Priority.
- `filler` – 1-bit-Rasterung von CozetteVector (`tools/ttf2bdf.py`) für
  px-Größen, die kein Kandidat erreicht.
- TTF-Outlines – das OTB ist ein sfnt mit leeren skalierbaren Glyphen; für
  Bitmap-unfähige Apps wird jede belegte Glyphe aus dem größten Strike
  getract (eine Rechteck-Kontur pro Tintenlauf pro Zeile) und in die
  `glyf`-Tabelle geschrieben. Die Bitmap-Strikes bleiben erhalten.

Strike-Plan ansehen, ohne zu bauen:

```sh
nix run .#dry-run
```

## Vorschau-Galerie

Rendert jeden Font in jeder nativen Größe (PNG, 1:1 + 3x-Zoom) und alle
Strikes des gemergten OTB.

```sh
nix build .#all-fonts-preview -o result-all-fonts-preview
# result-all-fonts-preview/share/muteshebbek/all-fonts-preview/index.html
```

## Checks

```sh
nix build .#checks.x86_64-linux.merged-valid   # und 8 weitere, siehe flake.nix
```

`manifest-exists`, `sizes-db-valid`, `priority-valid`, `merge-valid`,
`manifest-consistent`, `merged-valid`, `merged-render`, `outline-ttf`,
`previews-valid` – vom Manifest über die gemessenen Größen und den Merge bis
zur Renderbarkeit von OTB und TTF.

## Weitere Pakete

- `sizes-db` / `merge-sizes-db` – gemessene Größen aus den echten
  Datei-Headern (`tools/scan-sizes.py`), inkl. Abgleich gegen `fonts.json`
- `merge-winners` – generierte `winners.json` (Gewinner pro px)
- `fonts-manifest` – `fonts.json` als Store-Pfad
- jeder Font der Sammlung einzeln (`nix build .#cozette`, `.#tewi`, …)
- `devShell` – fontforge, bdf2sfd, bdftopcf, fonttools, bdffont,
  pixel-font-builder

## Font hinzufügen

1. Eintrag in `fonts.json` (`name`, `sizes_px`, `cell`, `origin`, Quellen,
   Preview-Link) – die Größen müssen zu den echten Datei-Headern passen
   (`manifest-consistent` prüft das).
2. Paket bauen: vorhandenes nixpkgs-Paket in `nixpkgsFonts` eintragen oder in
   `customFonts` (`mkTecateFont` für die Tecate-Sammlung, sonst Fetch).
3. Namen in `priority` aufnehmen, sonst gewinnt der Font nie und wird nicht in
   den Merge gebaut. Optional `upscaleForced` fürs Hochskalieren ohne nativen
   Gewinn.

## Repo

- `flake.nix` – Pakete (nixpkgs-first, Rest per Fetch), Merge-Konfiguration,
  Checks, Apps
- `fonts.json` – Manifest der Sammlung inkl. `sizes_px` und Preview-Links
- `tools/` – Python: `scan-sizes.py` (Größen messen), `build-merged.py`
  (Merge), `ttf2bdf.py` (Filler-Rasterung), `render-previews.py` (Galerie),
  `check-*.py` (Validierung)
- `Vorschaulinks.md` – Original-Previews der Upstreams

Die Lizenzen kommen mit den jeweiligen Fonts; pro Paket in `flake.nix`
hinterlegt (`meta.license`).
