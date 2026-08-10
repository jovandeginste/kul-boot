{
  description = "KU Leuven punk Plymouth theme flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      themeName = "kuleuven-punk";
      frameCount = 300;
      threshold = 16;
      changeProbability = 0.005;
      maxFlickerFrames = 4;
      featherMargin = 4;
      neonThreshold = 0;
      neonAlphaThreshold = 1;
      neonFeatherMargin = 6;
      neonPeriod = 35;
      neonMinScale = 0.55;
      neonMaxScale = 1.6;
      logoThreshold = 0;
      logoAlphaThreshold = 1;
      logoFeatherMargin = 6;
      logoFlickerProbability = 0.02;
      logoMinFlickerFrames = 2;
      logoMaxFlickerFrames = 9;
      logoFlickerOnProbability = 0.25;
      fps = 10;
      background = "0x000000";
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
              --count ${toString frameCount} \
              --jobs ''${NIX_BUILD_CORES:-1} \
              --threshold ${toString threshold} \
              --change-probability ${toString changeProbability} \
              --max-flicker-frames ${toString maxFlickerFrames} \
              --feather-margin ${toString featherMargin} \
              --neon-threshold ${toString neonThreshold} \
              --neon-alpha-threshold ${toString neonAlphaThreshold} \
              --neon-feather-margin ${toString neonFeatherMargin} \
              --neon-period ${toString neonPeriod} \
              --neon-min-scale ${toString neonMinScale} \
              --neon-max-scale ${toString neonMaxScale} \
              --logo-threshold ${toString logoThreshold} \
              --logo-alpha-threshold ${toString logoAlphaThreshold} \
              --logo-feather-margin ${toString logoFeatherMargin} \
              --logo-flicker-probability ${toString logoFlickerProbability} \
              --logo-min-flicker-frames ${toString logoMinFlickerFrames} \
              --logo-max-flicker-frames ${toString logoMaxFlickerFrames} \
              --logo-flicker-on-probability ${toString logoFlickerOnProbability}

            ${python}/bin/python "$src/generate_plymouth_theme.py" \
              --frames-dir "$workdir/frames" \
              --output-dir "$workdir/theme" \
              --theme-name ${themeName} \
              --fps ${toString fps} \
              --background ${background}

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
          "kuleuven-punk-plymouth" = themePackage;
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
        "kuleuven-punk-plymouth" = mkThemePackage final;
        "${themeName}" = mkThemePackage final;
      };

      nixosModules.default = { config, lib, pkgs, ... }:
        let
          cfg = config.services.kulBoot.plymouth;
        in {
          options.services.kulBoot = {
            plymouth = {
              enable = lib.mkEnableOption "the KU Leuven punk Plymouth theme";

              package = lib.mkOption {
                type = lib.types.package;
                default = self.packages.${pkgs.system}."kuleuven-punk-plymouth";
                description = "Plymouth theme package to install.";
              };
            };
          };

          config = lib.mkIf cfg.enable {
            boot.plymouth.enable = true;
            boot.plymouth.theme = themeName;
            boot.plymouth.themePackages = [ cfg.package ];
            boot.consoleLogLevel = 3;
            boot.kernelParams = [
              "quiet"
              "loglevel=3"
              "rd.udev.log_level=3"
              "udev.log_priority=3"
            ];
          };
        };
    };
}
