{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.poetry2nix.url = "github:nix-community/poetry2nix";

  outputs = { self, nixpkgs, poetry2nix }:
    let
      supportedSystems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      pkgs = forAllSystems (system: nixpkgs.legacyPackages.${system});
      over = p: final: prev: {
        charset-normalizer = p.python313Packages.charset-normalizer;
        paho-mqtt = prev.paho-mqtt.overridePythonAttrs (p: {
          buildInputs = (p.buildInputs or []) ++ [prev.hatchling];
          preferWheel = true;
        });
      };
    in
    {
      packages = forAllSystems (system: let
        inherit (poetry2nix.lib.mkPoetry2Nix { pkgs = pkgs.${system}; }) mkPoetryApplication;
      in {
        default = mkPoetryApplication { projectDir = self; };
      });

      devShells = forAllSystems (system: let
        inherit (poetry2nix.lib.mkPoetry2Nix { pkgs = pkgs.${system}; }) mkPoetryEnv overrides;
      in {
        default = pkgs.${system}.mkShellNoCC {
          packages = with pkgs.${system}; [
            (mkPoetryEnv { projectDir = self; overrides = overrides.withDefaults (over pkgs.${system}); })
            poetry
            pyright
          ];
        };
      });
    };
}
