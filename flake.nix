{
  description = "KU Leuven punk Plymouth theme flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      themeName = "kuleuven-punk";
      mkThemePackage = pkgs:
        let
          python = pkgs.python3.withPackages (ps: with ps; [
            pillow
          ]);
        in
        pkgs.stdenvNoCC.mkDerivation {
          pname = "plymouth-theme-${themeName}";
          version = "0.1.0";
          src = self;

          nativeBuildInputs = [ python ];

          dontConfigure = true;
          dontBuild = true;

          installPhase = ''
            runHook preInstall

            workdir="$(mktemp -d)"

            ${python}/bin/python "$src/generate_tl_flicker.py" \
              --base "$src/kuleuven-punk.png" \
              --mask "$src/kuleuven-punk-tl.png" \
              --neon-mask "$src/kuleuven-punk-neon-border.png" \
              --logo-mask "$src/kuleuven-punk-neon-logo.png" \
              --output-dir "$workdir/frames" \
              --count 300 \
              --jobs 1 \
              --threshold 16 \
              --change-probability 0.005 \
              --max-flicker-frames 4 \
              --feather-margin 4 \
              --neon-threshold 0 \
              --neon-alpha-threshold 1 \
              --neon-feather-margin 6 \
              --neon-period 35 \
              --neon-min-scale 0.55 \
              --neon-max-scale 1.6 \
              --logo-threshold 0 \
              --logo-alpha-threshold 1 \
              --logo-feather-margin 6 \
              --logo-flicker-probability 0.02 \
              --logo-min-flicker-frames 2 \
              --logo-max-flicker-frames 9 \
              --logo-flicker-on-probability 0.25 \
              --seed 1

            ${python}/bin/python "$src/generate_plymouth_theme.py" \
              --frames-dir "$workdir/frames" \
              --output-dir "$workdir/theme" \
              --theme-name ${themeName} \
              --fps 10 \
              --background 0x000000

            mkdir -p "$out/share/plymouth/themes/${themeName}"
            cp -r "$workdir/theme/"* "$out/share/plymouth/themes/${themeName}/"

            runHook postInstall
          '';

          meta = {
            description = "Animated Plymouth theme generated from KU Leuven punk neon artwork";
            platforms = pkgs.lib.platforms.linux;
          };
        };
    in
    (flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (ps: with ps; [
          pillow
        ]);
        themePackage = mkThemePackage pkgs;
      in {
        packages = {
          "${themeName}" = themePackage;
          default = themePackage;
        };

        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.ffmpeg
          ];
        };
      }
    ))
    // {
      overlays.default = final: _prev: {
        "${themeName}" = mkThemePackage final;
      };

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.kuleuvenPunkPlymouth;
        in {
          options.services.kuleuvenPunkPlymouth = {
            enable = lib.mkEnableOption "the KU Leuven punk Plymouth theme";

            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${pkgs.system}.${themeName};
              description = "Plymouth theme package to install.";
            };
          };

          config = lib.mkIf cfg.enable {
            boot.plymouth.enable = lib.mkDefault true;
            boot.plymouth.theme = themeName;
            boot.plymouth.themePackages = [ cfg.package ];
          };
        };
    };
}
