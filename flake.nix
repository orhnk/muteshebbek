{
  description = "muteshebbek - 60+ Bitmap-Fonts in einem Flake: nixpkgs-first, sonst Fetch vom Original (pixel-perfect Sammlung fuer Size-Select-Merge)";

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
          # Merge-Konfiguration: Single Source of Truth fuer den Merge. Was
          # frueher in priority.json / merge.json / upscale.json stand, lebt
          # jetzt hier; die Python-Tools bekommen daraus generierte JSONs.
          # ------------------------------------------------------------------
          #
          # 7,8 misc-fixed-ucs-7px
          # 9 tamsyn
          # 10, uushi-lemon
          # 11, dweep-11px
          # 12, orp-font-12px
          # 13, cozette
          # 15, sq
          # * , cozettevector
          # 
          priority = [
            "misc-fixed-ucs" "tamsyn" "cozette" "uushi-lemon" "dweep" "sq" 
            # "tewi" "scientifica" "kakwa" "cherry-bitmap" "profont" "montecarlo"
            # "proggyfonts" "termsyn" "terminusmod" "ohsnap" "kirsch"
            # "tamzen" "gohufont" "creep2" "envypn" "dina" "unscii"
            # --- Rest vorerst aus dem Merge ausgeschlossen ---
            # (weglassen = nie Gewinner, kein Upscale, nicht in neededPackages)
            # "ibmfonts" "artwiz-aleczapka" "tamsynmod"
            # "stlarch-font" "fixedsys-excelsior" "font-3270" "gomme"
            # "knxt" "haxor" "lode" "leggie" "vt323" "zevv-peep"
            # "press-start-2p" "silkscreen" "font-04b-03" "terminus" "spleen"
            # --- Erweiterung: weitere echte Bitmap-Fonts aus nixpkgs ---
            # "efont" "uw-ttyp0" "unifont" "ark-pixel"
            # --- Erweiterung: Tecate/bitmap-fonts Sammlung ---
            # "sgi" "mplus" "jmk-x11-fonts" "lokaltog-fonts" "ctrld-font"
            # "dylex" "raize" "bitocra" "speedy" "orp-font" "progsole"
            # "gilesorr" "opti" "pixelcarnage" "tobi" "erusfont" "trisk"
            # "boxxy" "kourier" "siji" "xbmicons" "clearlyu" "creep"
          ];

          # Pro-Font Groessenauswahl fuer den Merge, Format:
          #   "tamsyn:size=9,12,13"
          # Der Font darf dann nur bei diesen Groessen nativ gewinnen und
          # nur aus ihnen hochskaliert werden. Alle anderen echten Groessen
          # bleiben in `all`, aber nicht im Merge. Die Groessen muessen zur
          # fonts.json (echte Header) passen, sonst gibt es einen Fehler.
          sizeSelectEntries = [
            "tamsyn:size=9"
            "misc-fixed-ucs:size=7,8"
            "uushi-lemon:size=10"
            "dweep:size=11"
          ];
          parseSizeSelect = entry:
            let
              m = builtins.match "([^:]+):size=([0-9]+(,[0-9]+)*)" entry;
            in
              if m == null
              then throw "size_select: '${entry}' erwartet das Format 'font:size=9,12,13'"
              else {
                name = builtins.head m;
                sizes = lib.sort (a: b: a < b)
                  (lib.unique (map lib.toInt (lib.splitString "," (builtins.elemAt m 1))));
              };
          sizeSelect = builtins.listToAttrs (map
            (e: let p = parseSizeSelect e; in { name = p.name; value = p.sizes; })
            sizeSelectEntries);

          mergeCfg = {
            min_size_px = 7;
            max_size_px = 100;
            native_beats_scaled = true;
            upscale_scope = "winners";
            filler = { enabled = true; scope = "both"; font = "cozette-vector"; };
            max_strikes = 0;
            max_output_mb = 0;
            size_select = sizeSelect;
            inherit priority;
          };
          mergeJson = pkgs.writeText "merge.json" (builtins.toJSON mergeCfg);

          # Pakete, die auch ohne nativen Gewinn hochskaliert werden.
          # zevv-peep entfernt, weil es nicht mehr in der priority steht.
          upscaleForced = [ "dina" "uushi-lemon" "cherry-bitmap" "cozette" "tamzen" ];
          fillerPackage = "cozette";

          # Pure Gewinnerberechnung: pro Ziel-px gewinnt der hoechste
          # Priority-Eintrag, der die Groesse laut fonts.json nativ hat.
          # size_select schraenkt das pro Font auf die gewaehlten Groessen
          # ein (native Gewinner UND Scaled-Quellen).
          # Damit kennt Nix die benoetigten Pakete ohne jeden Font zu bauen.
          fontsManifest = builtins.fromJSON (builtins.readFile ./fonts.json);
          realSizesByPkg = builtins.listToAttrs
            (map (m: { name = m.name; value = m.sizes_px or []; }) fontsManifest);
          sizeSelectErrors = lib.flatten (lib.mapAttrsToList
            (name: sizes:
              if !(builtins.hasAttr name realSizesByPkg)
              then ["size_select: unbekannter Font '${name}'"]
              else map (s: "size_select: ${name} hat kein natives ${toString s}px")
                (builtins.filter (s: !(builtins.elem s realSizesByPkg.${name})) sizes))
            sizeSelect);
          sizesByPkg = if sizeSelectErrors == []
            then builtins.mapAttrs (name: real: sizeSelect.${name} or real) realSizesByPkg
            else throw (lib.concatStringsSep "\n" sizeSelectErrors);
          ownersFor = px: builtins.filter
            (n: builtins.elem px (sizesByPkg.${n} or [])) priority;
          decided = builtins.filter (w: w.contenders != [])
            (map (px: { inherit px; contenders = ownersFor px; })
              (lib.range mergeCfg.min_size_px mergeCfg.max_size_px));
          winnersObj = builtins.listToAttrs (map (w: {
            name = toString w.px;
            value = { winner = builtins.head w.contenders; contenders = w.contenders; };
          }) decided);
          winnersJson = pkgs.writeText "winners.json" (builtins.toJSON {
            generated_by = "flake.nix from fonts.json + priority + size_select";
            inherit (mergeCfg) min_size_px max_size_px;
            winners = winnersObj;
          });
          # Nur die tatsaechlich gebrauchten Font-Pakete baut der Merge.
          neededPackages = lib.unique (
            map (w: builtins.head w.contenders) decided
            ++ upscaleForced
            ++ lib.optional mergeCfg.filler.enabled fillerPackage);

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
            # --- weitere echte Bitmap-Fonts direkt aus nixpkgs ---
            efont = pkgs.efont-unicode; # 10/12/14/16/24px (BDF/PCF/OTB, efont japanisch)
            uw-ttyp0 = pkgs.uw-ttyp0; # 11..18/22px (PCF/OTB/PSF)
            unifont = pkgs.unifont; # 16px (BDF/PCF/OTB, GNU Unifont)
            ark-pixel = pkgs.ark-pixel-font; # 10/12/16px (BDF/PCF + OTF/TTF)
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
            # --- weitere Fonts der Tecate/bitmap-fonts Sammlung ---
            bitocra = mkTecateFont "bitocra" "bitocra" "2024"; # 4/5/7/10/11/13px
            boxxy = mkTecateFont "boxxy" "boxxy" "2024"; # 14px
            clearlyu = mkTecateFont "clearlyu" "clearlyu" "2024"; # 17px
            ctrld-font = mkTecateFont "ctrld-font" "ctrld-font" "2024"; # 10/13/16px
            dylex = mkTecateFont "dylex" "dylex" "2024"; # 10/13/14/20px
            erusfont = mkTecateFont "erusfont" "erusfont" "2024"; # 11px
            gilesorr = mkTecateFont "gilesorr" "gilesorr" "2024"; # 10px
            jmk-x11-fonts = mkTecateFont "jmk-x11-fonts" "jmk-x11-fonts-3.0" "3.0"; # 10/11/13/15/20/24px
            kourier = mkTecateFont "kourier" "kourier" "2024"; # 15px
            lokaltog-fonts = mkTecateFont "lokaltog-fonts" "lokaltog-fonts" "2024"; # 10/11/12px
            mplus = mkTecateFont "mplus" "mplus" "2024"; # 6/10/12px
            opti = mkTecateFont "opti" "opti" "2024"; # 11px
            orp-font = mkTecateFont "orp-font" "orp-font" "2024"; # 12px
            pixelcarnage = mkTecateFont "pixelcarnage" "pixelcarnage" "2024"; # 14px
            progsole = mkTecateFont "progsole" "progsole" "2024"; # 10px
            raize = mkTecateFont "raize" "raize" "2024"; # 13/14/17/19px
            sgi = mkTecateFont "sgi" "sgi" "2024"; # 7..16/18/24/36px (IRIX)
            siji = mkTecateFont "siji" "siji" "2024"; # 10px (Icon-Font)
            speedy = mkTecateFont "speedy" "speedy" "2024"; # 11/12px
            sq = mkTecateFont "sq" "sq" "2024"; # 15px
            tobi = mkTecateFont "tobi" "tobi" "2024"; # 12px
            trisk = mkTecateFont "trisk" "trisk" "2024"; # 13px
            xbmicons = mkTecateFont "xbmicons" "xbmicons" "2024"; # 12px (Icon-Font)
          };

          allFontsList = (builtins.attrValues nixpkgsFonts) ++ (builtins.attrValues customFonts);
          namedFonts = nixpkgsFonts // customFonts;

          # pkgmap nur fuer die gebrauchten Pakete -> merged baut nur diese.
          neededPkgMapTxt = pkgs.writeText "pkgmap-merged.txt"
            (lib.concatMapStringsSep "\n"
              (logical: "${namedFonts.${logical}} ${logical}")
              neededPackages);

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
          sizesScanPython = pkgs.python3.withPackages (ps: with ps; [ fonttools freetype-py ]);
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
                --out "$out/share/muteshebbek/sizes.json" \
                --summary "$out/share/muteshebbek/summary.json" \
                --compare "$out/share/muteshebbek/sizes-compare.txt"
              runHook postInstall
            '';
            meta = with lib; {
              description = "sizes.json: reale Groessen aller lokalen Font-Dateien (BDF/PCF/OTB/TTF/PSF-Header)";
              license = licenses.free;
            };
          };

          # ---- merge-sizes-db: gleiche Messung, aber nur ueber die Pakete,
          # die der Merge wirklich braucht. merged haengt dadurch nicht an
          # allen 41 Font-Paketen.
          mergeSizesDb = pkgs.stdenvNoCC.mkDerivation {
            pname = "muteshebbek-merge-sizes-db";
            version = "1";
            src = ./tools/scan-sizes.py;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            nativeBuildInputs = [ sizesScanPython ];
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/muteshebbek"
              python3 "$src" --pkgmap ${neededPkgMapTxt} --manifest ${./fonts.json} \
                --out "$out/share/muteshebbek/sizes.json" \
                --summary "$out/share/muteshebbek/summary.json" \
                --compare "$out/share/muteshebbek/sizes-compare.txt"
              runHook postInstall
            '';
            meta = with lib; {
              description = "sizes.json nur fuer die Merge-Pakete (von flake.nix aus fonts.json+priority gewaehlt)";
              license = licenses.free;
            };
          };

          # ---- merged: DER Font. Ein Strike pro px, Gewinner per priority.
          # Zusaetzlich ein TTF mit echten glyf-Outlines (aus dem jeweils
          # groessten Bitmap-Strike getraced) fuer Apps ohne Bitmap-/OTB-
          # Support; die Bitmap-Strikes bleiben im TTF erhalten.
          # Filler-TTF: wird fuer px-Luecken (kein Bitmap-Font erreichbar)
          # 1-bit gerastert und als zusaetzlicher Strike eingemerged.
          fillerTtf = "${namedFonts.cozette}/share/fonts/truetype/CozetteVector.ttf";
          merged = pkgs.stdenvNoCC.mkDerivation {
            pname = "muteshebbek";
            version = "6";
            src = ./tools;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            nativeBuildInputs = [ sizesScanPython pkgs.xorg.fonttosfnt ];
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/fonts/OTB" "$out/share/fonts/TTF" "$out/share/muteshebbek"
              python3 "$src/build-merged.py" --pkgmap ${neededPkgMapTxt} \
                --sizes ${mergeSizesDb}/share/muteshebbek/sizes.json \
                --winners ${winnersJson} \
                --merge ${mergeJson} \
                --force ${lib.escapeShellArgs upscaleForced} \
                --filler-ttf "${fillerTtf}" \
                --out "$out/share/fonts/OTB/Muteshebbek.otb" \
                --out-ttf "$out/share/fonts/TTF/Muteshebbek.ttf" \
                --report "$out/share/muteshebbek/merged-report.json"
              runHook postInstall
            '';
            meta = with lib; {
              description = "Muteshebbek: die gebrauchten Bitmap-Fonts in einem OTB plus Outline-TTF, ein Strike pro px-Groesse (Gewinner per priority in flake.nix)";
              license = licenses.free;
            };
          };

          # ---- all-fonts-preview: Galerie aller Fonts in allen nativen
          # px-Groessen (BDF/PCF per Pillow gerendert, 1:1 + 3x-Zoom) plus
          # alle Strikes des gemergten OTB. Aufruf:
          #   nix build .#all-fonts-preview -o result-all-fonts-preview
          previewsPython = pkgs.python3.withPackages (ps: with ps; [ fonttools pillow ]);
          allFontsPreview = pkgs.stdenvNoCC.mkDerivation {
            pname = "muteshebbek-all-fonts-preview";
            version = "1";
            src = ./tools/render-previews.py;
            dontUnpack = true;
            dontConfigure = true;
            dontBuild = true;
            nativeBuildInputs = [ previewsPython ];
            installPhase = ''
              runHook preInstall
              mkdir -p "$out/share/muteshebbek"
              python3 "$src" --pkgmap ${pkgMapTxt} \
                --sizes ${sizesDb}/share/muteshebbek/sizes.json \
                --merged-otb ${merged}/share/fonts/OTB/Muteshebbek.otb \
                --merged-report ${merged}/share/muteshebbek/merged-report.json \
                --outdir "$out/share/muteshebbek/all-fonts-preview"
              runHook postInstall
            '';
            meta = with lib; {
              description = "Muteshebbek Vorschau-Galerie: jeder Font in jeder nativen px-Groesse (PNG + index.html)";
              license = licenses.free;
              platforms = platforms.all;
            };
          };

          manifest = ./fonts.json;
        in
        {
          packages = namedFonts // {
            inherit all merged;
            "sizes-db" = sizesDb;
            "merge-sizes-db" = mergeSizesDb;
            "merge-winners" = winnersJson;
            "all-fonts-preview" = allFontsPreview;
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

          # ---- dry-run: welche Source-Font gewinnt pro px (baut nichts).
          # Aufruf: nix run .#dry-run  (liest winnersJson + merge-sizes-db)
          apps.dry-run =
            let
              dry-run-prog = pkgs.writeShellScriptBin "muteshebbek-dry-run" ''
                exec ${sizesScanPython}/bin/python3 ${./tools/build-merged.py} --dry-run \
                  --sizes ${mergeSizesDb}/share/muteshebbek/sizes.json \
                  --winners ${winnersJson} \
                  --merge ${mergeJson} \
                  --force ${lib.escapeShellArgs upscaleForced} \
                  --filler-ttf "${fillerTtf}"
              '';
            in
            {
              type = "app";
              program = "${dry-run-prog}/bin/muteshebbek-dry-run";
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
              python3 ${./tools/check-priority.py} ${mergeJson} ${lib.escapeShellArgs (builtins.attrNames namedFonts)}
              touch "$out"
            '';
            merge-valid = pkgs.runCommand "check-merge"
              { nativeBuildInputs = [ sizesScanPython ]; } ''
              python3 ${./tools/check-merge.py} ${mergeJson}
              touch "$out"
            '';
            # fonts.json ist die Quelle der Merge-Entscheidung -> deklarierte
            # Groessen muessen zu den echten Headern passen.
            manifest-consistent = pkgs.runCommand "check-manifest-consistent" { } ''
              if grep -q '^MISMATCH' ${sizesDb}/share/muteshebbek/sizes-compare.txt; then
                echo "fonts.json sizes_px is out of sync with the real headers:" >&2
                grep '^MISMATCH' ${sizesDb}/share/muteshebbek/sizes-compare.txt >&2
                exit 1
              fi
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
            outline-ttf = pkgs.runCommand "check-outline-ttf"
              { nativeBuildInputs = [ sizesScanPython ]; } ''
              python3 ${./tools/check-ttf.py} ${merged}/share/fonts/TTF/Muteshebbek.ttf ${merged}/share/muteshebbek/merged-report.json
              touch "$out"
            '';
            previews-valid = pkgs.runCommand "check-previews"
              { nativeBuildInputs = [ previewsPython ]; } ''
              python3 ${./tools/check-previews.py} ${allFontsPreview}/share/muteshebbek/all-fonts-preview
              touch "$out"
            '';
          };
        };
    in
    {
      packages = forEachSystem (pkgs: (mkSystem pkgs).packages);
      devShells = forEachSystem (pkgs: (mkSystem pkgs).devShells);
      checks = forEachSystem (pkgs: (mkSystem pkgs).checks);
      apps = forEachSystem (pkgs: (mkSystem pkgs).apps);
    };
}
