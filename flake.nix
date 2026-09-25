{
  description = "muteshebbek - 40+ Bitmap-Fonts in einem Flake: nixpkgs-first, sonst Fetch vom Original (pixel-perfect Sammlung fuer Size-Select-Merge)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forEachSystem = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));

      # Helper: installiere BDF/PCF/OTB/TTF/PSF/FON aus einem Verzeichnis nach share/fonts.
      # Rekursiv bis Tiefe 2 (z.B. montecarlo/bdf/*.bdf), Dateinamen mit
      # Leerzeichen sind ok (find -exec).
      installFonts = ''
        mkdir -p "$out/share/fonts/misc" "$out/share/fonts/OTB" "$out/share/fonts/TTF" "$out/share/fonts/psf"
        find . -maxdepth 2 -type f \( -name '*.bdf' -o -name '*.pcf' -o -name '*.pcf.gz' \) -exec cp -t "$out/share/fonts/misc/" {} +
        find . -maxdepth 2 -type f \( -name '*.otb' -o -name '*.otf' \) -exec cp -t "$out/share/fonts/OTB/" {} +
        find . -maxdepth 2 -type f -name '*.ttf' -exec cp -t "$out/share/fonts/TTF/" {} +
        find . -maxdepth 2 -type f \( -name '*.psf' -o -name '*.psfu' -o -name '*.psfu.gz' -o -name '*.psf.gz' -o -name '*.fnt' -o -name '*.fon' -o -name '*.dfont' \) -exec cp -t "$out/share/fonts/psf/" {} +
      '';

      mkSystem = pkgs:
        let
          lib = pkgs.lib;

          # ------------------------------------------------------------------
          # 1) Direkt aus nixpkgs (Regel: wenn in nixpkgs vorhanden, NICHT fetchen)
          # ------------------------------------------------------------------
          nixpkgsFonts = {
            terminus = pkgs.terminus_font; # 12..32px, 6x12..16x32
            spleen = pkgs.spleen; # 8,12,16,24,32,64px
            gohufont = pkgs.gohufont; # 11,14px
            tamzen = pkgs.tamzen; # 9,12,13,14,15,16,20px
            tamsyn = pkgs.tamsyn; # dto. (Upstream)
            cozette = pkgs.cozette; # 13px + HiDPI 26px
            scientifica = pkgs.scientifica; # ~11px
            creep = pkgs.creep; # 16px (romeovs)
            unscii = pkgs.unscii; # 8px + 16px Varianten
            proggyfonts = pkgs.proggyfonts; # Clean/Tiny/Small/Square 10-13px
            dina = pkgs.dina-font; # 8/9px BDF + TTF
            profont = pkgs.profont; # 11/12px
            termsyn = pkgs.termsyn; # 12px
            # kirsch gibt es in nixos-25.05 noch nicht (erst ab ~26.05) ->
            # Regel: nixpkgs wenn vorhanden, sonst Fetch vom Release.
            kirsch = if builtins.hasAttr "kirsch" pkgs then pkgs.kirsch else pkgs.stdenvNoCC.mkDerivation {
              pname = "kirsch";
              version = "0.7.3";
              src = pkgs.fetchzip {
                url = "https://github.com/molarmanful/kirsch/releases/download/v0.7.3/kirsch-release_v0.7.3.zip";
                hash = "sha256-j7LMtOQqOl4aTDf/ytVci2M2plFliLkswRsQhY1EWC4=";
              };
              dontConfigure = true;
              dontBuild = true;
              installPhase = ''
                runHook preInstall
                cd "$src"
                ${installFonts}
                runHook postInstall
              '';
              meta = with pkgs.lib; {
                description = "Kirsch bitmap font 16px (6x16) + 2x/3x HiDPI (Fallback-Fetch, nixpkgs-25.05)";
                homepage = "https://github.com/molarmanful/kirsch";
                license = licenses.ofl;
                platforms = platforms.all;
              };
            };
            vt323 = pkgs.vt323; # ~16px
            fixedsys-excelsior = pkgs.fixedsys-excelsior; # 12/16px
            font-3270 = pkgs._3270font; # 12/16px (rbanffy)
            envypn = pkgs.envypn-font; # 13/15px
          };

          # ------------------------------------------------------------------
          # 2) NICHT (brauchbar) in nixpkgs -> Fetch vom Original
          # ------------------------------------------------------------------
          tecateSrc = pkgs.fetchFromGitHub {
            owner = "Tecate";
            repo = "bitmap-fonts";
            rev = "master";
            hash = "sha256-1FUNybNCD1OVSgAMYkgyyGQmjmRWTu6YhjD7YelPIWg=";
          };

          # Ein Tecate-Unterordner als eigenes Font-Paket (tewi, ohsnap, ...).
          # Grund: tewi-font wurde aus nixpkgs entfernt (upstream archiviert),
          # ohsnap/montecarlo/stlarch/terminusmod/tamsynmod/gomme/... gibt es
          # in nixpkgs gar nicht erst.
          mkTecateFont = name: subdir: version: pkgs.stdenvNoCC.mkDerivation {
            pname = name;
            inherit version;
            src = tecateSrc;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              srcdir="$src/bitmap/${subdir}"
              if [ ! -d "$srcdir" ]; then echo "missing subdir: $srcdir"; ls "$src/bitmap" | head -60; exit 1; fi
              cd "$srcdir"
              ${installFonts}
              runHook postInstall
            '';
            meta = with lib; {
              description = "Bitmap font ${name} (via Tecate/bitmap-fonts Sammlung, Original: siehe fonts.json)";
              homepage = "https://github.com/Tecate/bitmap-fonts";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          cherrySrc = pkgs.fetchFromGitHub {
            owner = "MarinHoc";
            repo = "cherry";
            rev = "master";
            # HINWEIS: nixpkgs 'cherry' ist turquoise-hexagon/cherry (Vektor),
            # NICHT MarinHoc/cherry (Bitmap 10/11/12/13px) -> daher Custom-Fetch.
            hash = "sha256-rTDYo0GP43FSkwfiaT4u+3mUCufXGxpespmx3w24vpw=";
          };
          cherry-bitmap = pkgs.stdenvNoCC.mkDerivation {
            pname = "cherry-bitmap";
            version = "2024-05-17";
            src = cherrySrc;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              cd "$src"
              ${installFonts}
              runHook postInstall
            '';
            meta = with lib; {
              description = "Cherry bitmap font 10/11/12/13px (MarinHoc)";
              homepage = "https://github.com/MarinHoc/cherry";
              license = licenses.mit;
              platforms = platforms.all;
            };
          };

          creep2Src = pkgs.fetchFromGitHub {
            owner = "raymond-w-ko";
            repo = "creep2";
            rev = "master";
            hash = "sha256-iVppvnqgui/KUZTqYeEX9Qw8k325ix40+AVG49qmGVw=";
          };
          creep2 = pkgs.stdenvNoCC.mkDerivation {
            pname = "creep2";
            version = "unstable-2024";
            src = creep2Src;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              cd "$src"
              ${installFonts}
              runHook postInstall
            '';
            meta = with lib; {
              description = "Creep2 bitmap font 11px (creep-Nachfolger)";
              homepage = "https://github.com/raymond-w-ko/creep2";
              license = licenses.mit;
              platforms = platforms.all;
            };
          };

          ibmfontsSrc = pkgs.fetchFromGitHub {
            owner = "farsil";
            repo = "ibmfonts";
            rev = "master";
            hash = "sha256-fX9GUfRkoxWXY865R+VHd2GkW0qfMMQbG/0y3Lu+YQU=";
          };
          ibmfonts = pkgs.stdenvNoCC.mkDerivation {
            pname = "ibmfonts";
            version = "unstable-2024";
            src = ibmfontsSrc;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              cd "$src/bdf"
              ${installFonts}
              runHook postInstall
            '';
            meta = with lib; {
              description = "IBM BIOS/VGA/CGA BDF fonts 8x8/8x14/8x16/9x14/9x16 (farsil)";
              homepage = "https://github.com/farsil/ibmfonts";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          press-start-2p = pkgs.stdenvNoCC.mkDerivation {
            pname = "press-start-2p";
            version = "google-fonts-2024";
            src = pkgs.fetchurl {
              url = "https://raw.githubusercontent.com/google/fonts/main/ofl/pressstart2p/PressStart2P-Regular.ttf";
              hash = "sha256-A0x38fBeyJQh5KY/DjpMoez4UsxtK/YR8SbydXKOAX0=";
            };
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/fonts/TTF"
              cp -v "$src" "$out/share/fonts/TTF/PressStart2P-Regular.ttf"
              runHook postInstall
            '';
            meta = with lib; {
              description = "Press Start 2P 8px (codeman38, via google/fonts)";
              homepage = "https://github.com/codeman38/PressStart2P";
              license = licenses.ofl;
              platforms = platforms.all;
            };
          };

          silkscreen = pkgs.stdenvNoCC.mkDerivation {
            pname = "silkscreen";
            version = "google-fonts-2024";
            srcs = [
              (pkgs.fetchurl {
                url = "https://raw.githubusercontent.com/google/fonts/main/ofl/silkscreen/Silkscreen-Regular.ttf";
                hash = "sha256-yEVHMzC5TCB5zprwHFGsi6LZnCT00UwDmEO7uOZC69g=";
              })
              (pkgs.fetchurl {
                url = "https://raw.githubusercontent.com/google/fonts/main/ofl/silkscreen/Silkscreen-Bold.ttf";
                hash = "sha256-doR2qnEtT1w+GNO86A+YCovT9ytwlNIuxedo3zrP7WE=";
              })
            ];
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/fonts/TTF"
              for s in $srcs; do cp -v "$s" "$out/share/fonts/TTF/"; done
              runHook postInstall
            '';
            meta = with lib; {
              description = "Silkscreen 8px Regular+Bold (via google/fonts)";
              homepage = "https://github.com/google/fonts/tree/main/ofl/silkscreen";
              license = licenses.ofl;
              platforms = platforms.all;
            };
          };

          # Artwiz: Sourceforge-Mirror ist instabil (Hash wechselt je Mirror).
          # Stattdessen BDFs aus Tecate-Sammlung (Upstream: artwizaleczapka 1.3).
          artwiz-aleczapka = mkTecateFont "artwiz-aleczapka" "artwiz/bdf" "1.3";

          misc-fixed-ucs = pkgs.stdenvNoCC.mkDerivation {
            pname = "misc-fixed-ucs";
            version = "2024";
            src = pkgs.fetchurl {
              url = "http://www.cl.cam.ac.uk/~mgk25/download/ucs-fonts.tar.gz";
              hash = "sha256-cC/Rze+RI+GHFiKol3J5d8CTOkIMUMlBmPW7It6PD4o=";
            };
            dontConfigure = true;
            dontBuild = true;
            # Archiv hat mehrere Top-Level-Dateien (kein Root-Verzeichnis).
            unpackPhase = ''
              runHook preUnpack
              tar xzf "$src"
              runHook postUnpack
            '';
            installPhase = ''
              runHook preInstall
              ${installFonts}
              runHook postInstall
            '';
            meta = with lib; {
              description = "Misc-Fixed UCS fonts 4x6..10x20 (6,7,8,9,10,12,13,14,15,18,20px)";
              homepage = "http://www.cl.cam.ac.uk/~mgk25/ucs-fonts/";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          font-04b-03 = pkgs.stdenvNoCC.mkDerivation {
            pname = "font-04b-03";
            version = "dafont-2024";
            src = pkgs.fetchurl {
              url = "https://dl.dafont.com/dl/?f=04b_03";
              name = "04b_03.zip";
              hash = "sha256-51kmBAZ0vBnh5x1OkxtnPUCz6B2gB2P9Pp20jaeBLYg=";
            };
            nativeBuildInputs = with pkgs; [ unzip ];
            dontConfigure = true;
            dontBuild = true;
            unpackPhase = ''
              runHook preUnpack
              unzip -j "$src" -d .
              runHook postUnpack
            '';
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/fonts/TTF"
              cp -v ./*.TTF ./*.ttf "$out/share/fonts/TTF/" 2>/dev/null || true
              runHook postInstall
            '';
            meta = with lib; {
              description = "04b_03 pixel font 8px (dafont; Lizenz vor Merge pruefen)";
              homepage = "https://www.dafont.com/de/04b-03.font";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          customFonts = {
            inherit cherry-bitmap creep2 ibmfonts press-start-2p silkscreen artwiz-aleczapka misc-fixed-ucs font-04b-03;
            # Aus der Tecate-Sammlung (je ein Paket pro Font, gleiche Quelle):
            tewi = mkTecateFont "tewi" "tewi-font" "2024"; # 11px
            ohsnap = mkTecateFont "ohsnap" "ohsnap-1.8.0" "1.8.0"; # 11/12/13px
            montecarlo = mkTecateFont "montecarlo" "montecarlo" "2024"; # 11px
            terminusmod = mkTecateFont "terminusmod" "terminusmod-1.9.9" "1.9.9"; # 12px
            tamsynmod = mkTecateFont "tamsynmod" "tamsynmod-1.7" "1.7"; # 12px
            stlarch-font = mkTecateFont "stlarch-font" "stlarch" "2024"; # ~11px
            gomme = mkTecateFont "gomme" "gomme" "2024"; # 20px
            kakwa = mkTecateFont "kakwa" "kakwa" "2024"; # 12px
            knxt = mkTecateFont "knxt" "knxt" "2024"; # 20px (9x20)
            haxor = mkTecateFont "haxor" "haxor" "2024"; # 12/15px
            dweep = mkTecateFont "dweep" "dweep" "2024"; # ~12px
            lode = mkTecateFont "lode" "lode" "2024"; # 15px (aus screenshots/lode-15)
            leggie = mkTecateFont "leggie" "leggie" "2024";
            uushi-lemon = mkTecateFont "uushi-lemon" "phallus" "2024"; # lemon-10 + uushi-11
            zevv-peep = mkTecateFont "zevv-peep" "zevv-peep" "2024"; # 14px
          };

          allFontsList = (builtins.attrValues nixpkgsFonts) ++ (builtins.attrValues customFonts);
          namedFonts = nixpkgsFonts // customFonts;

          all = pkgs.symlinkJoin {
            name = "muteshebbek-bitmap-fonts-all";
            paths = allFontsList;
            meta = with lib; {
              description = "Alle Bitmap-Fonts vereint (nixpkgs-first, Rest per Fetch)";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          # ---- sizes-db: Groessen-Datenbank aus LOKALEN Headern (tools/scan-sizes.py)
          # pkgmap: eine Zeile pro Paket "<store-pfad> <logischer-name>"
          # (Attr-Namen duerfen keinen Store-Kontext tragen, daher Zeilenformat).
          pkgMapTxt = pkgs.writeText "pkgmap.txt"
            (lib.concatMapStringsSep "\n"
              (logical: "${namedFonts.${logical}} ${logical}")
              (builtins.attrNames namedFonts));
          sizesScanPython = pkgs.python3.withPackages (ps: with ps; [ fonttools ]);
          sizesDb = pkgs.stdenvNoCC.mkDerivation {
            pname = "muteshebbek-sizes-db";
            version = "1";
            src = ./tools/scan-sizes.py;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            nativeBuildInputs = [ sizesScanPython ];
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/muteshebbek"
              python3 "$src" --pkgmap ${pkgMapTxt} --manifest ${./fonts.json} \
                --priority ${./priority.json} \
                --out "$out/share/muteshebbek/sizes.json" \
                --summary "$out/share/muteshebbek/summary.json" \
                --compare "$out/share/muteshebbek/sizes-compare.txt" \
                --winners "$out/share/muteshebbek/winners.json"
              runHook postInstall
            '';
            meta = with lib; {
              description = "sizes.json: reale Groessen aller lokalen Font-Dateien (BDF/PCF/OTB/TTF/PSF-Header)";
              license = licenses.free;
            };
          };

          # ---- merged: DER Font. Ein Strike pro px, Gewinner per priority.
          merged = pkgs.stdenvNoCC.mkDerivation {
            pname = "muteshebbek";
            version = "2";
            src = ./tools/build-merged.py;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            nativeBuildInputs = [ sizesScanPython pkgs.xorg.fonttosfnt ];
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/fonts/OTB" "$out/share/muteshebbek"
              python3 "$src" --pkgmap ${pkgMapTxt} \
                --sizes ${sizesDb}/share/muteshebbek/sizes.json \
                --winners ${sizesDb}/share/muteshebbek/winners.json \
                --out "$out/share/fonts/OTB/Muteshebbek.otb" \
                --report "$out/share/muteshebbek/merged-report.json"
              runHook postInstall
            '';
            meta = with lib; {
              description = "Muteshebbek: alle Bitmap-Fonts in einem OTB, ein Strike pro px-Groesse (Gewinner per priority.json)";
              license = licenses.free;
            };
          };

          manifest = ./fonts.json;
        in
        {
          packages = namedFonts // {
            inherit all merged;
            "sizes-db" = sizesDb;
            default = all;
            fonts-manifest = pkgs.stdenvNoCC.mkDerivation {
              pname = "muteshebbek-fonts-manifest";
              version = "1";
              src = ./fonts.json;
              dontUnpack = true;
              dontConfigure = true;
              dontBuild = true;
              installPhase = ''
                mkdir -p "$out/share/muteshebbek"
                cp -v "$src" "$out/share/muteshebbek/fonts.json"
              '';
              meta = with pkgs.lib; {
                description = "fonts.json Manifest (Groessen/Quellen/Previews) fuer den Size-Select-Merge";
                license = licenses.free;
              };
            };
          };

          devShells.default = pkgs.mkShell {
            packages = with pkgs; [
              fontforge
              bdf2sfd
              xorg.bdftopcf
              xorg.mkfontdir
              xorg.fonttosfnt
              (python3.withPackages (ps: with ps; [ fonttools bdffont pixel-font-builder ]))
            ] ++ lib.optional (builtins.hasAttr "bitsnpicas" pkgs) pkgs.bitsnpicas;
            shellHook = ''
              echo "muteshebbek dev-shell: fontforge, bdf2sfd, bdftopcf, fonttools/bdffont/pixel-font-builder bereit."
              echo "Sammlung bauen: nix build .#all   |   Manifest: cat fonts.json"
            '';
          };

          checks = {
            manifest-exists = pkgs.runCommand "check-manifest" { } ''
              test -f ${manifest} && touch "$out"
            '';
            sizes-db-valid = pkgs.runCommand "check-sizes-db"
              { nativeBuildInputs = [ sizesScanPython ]; } ''
              python3 ${./tools/check-sizes.py} ${sizesDb}/share/muteshebbek/sizes.json
              python3 -c "import json; s=json.load(open('${sizesDb}/share/muteshebbek/summary.json')); assert s['total_files']>0, 'empty summary'; print('summary OK:', s['total_files'], 'files')"
              touch "$out"
            '';
            priority-valid = pkgs.runCommand "check-priority"
              { nativeBuildInputs = [ sizesScanPython ]; } ''
              python3 ${./tools/check-priority.py} ${./priority.json} ${lib.escapeShellArgs (builtins.attrNames namedFonts)}
              touch "$out"
            '';
            merged-valid = pkgs.runCommand "check-merged"
              { nativeBuildInputs = [ sizesScanPython ]; } ''
              python3 ${./tools/check-merged.py} ${merged}/share/fonts/OTB/Muteshebbek.otb ${merged}/share/muteshebbek/merged-report.json
              touch "$out"
            '';
            merged-render = pkgs.runCommand "check-merged-render"
              { nativeBuildInputs = [ (pkgs.python3.withPackages (ps: with ps; [ pillow ])) ]; } ''
              python3 ${./tools/check-render.py} ${merged}/share/fonts/OTB/Muteshebbek.otb ${merged}/share/muteshebbek/merged-report.json
              touch "$out"
            '';
          };
        };
    in
    {
      packages = forEachSystem (pkgs: (mkSystem pkgs).packages);
      devShells = forEachSystem (pkgs: (mkSystem pkgs).devShells);
      checks = forEachSystem (pkgs: (mkSystem pkgs).checks);
    };
}
