{
  description = "TL flicker image generator environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (ps: with ps; [
          pillow
        ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = [
            python
            pkgs.ffmpeg
          ];
        };
      }
    );
}
