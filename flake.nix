{
  description = "Experiment generator for the graph partitioner KaMinPar";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs { inherit system; };

      inputs = builtins.attrValues {
        inherit (pkgs) cmake ninja python3 gcc14 tbb_2021_11 sparsehash mpi numactl pkg-config time;
        inherit (pkgs.llvmPackages_18) openmp;
      };

      devShellInputs = builtins.attrValues {
        inherit (pkgs) fish ruff ccache;
      };
    in
    {
      devShells = rec {
        default = gcc;

        gcc = pkgs.mkShell {
          packages = inputs ++ devShellInputs;

          shellHook = ''
            exec fish
          '';
        };

        clang = (pkgs.mkShell.override { stdenv = pkgs.llvmPackages_18.stdenv; }) {
          packages = (pkgs.lib.lists.remove pkgs.gcc14 inputs) ++ devShellInputs;

          shellHook = ''
            exec fish
          '';
        };
      };

      packages.default = pkgs.stdenvNoCC.mkDerivation {
        pname = "kmpexp";
        version = "1.0.0";

        src = self;
        buildInputs = inputs;

        dontConfigure = true;
        dontBuild = true;

        installPhase = ''
          mkdir -p $out/bin
          cp -r $src/* $out/bin
        '';

        meta = {
          description = "Experiment generator for the graph partitioner KaMinPar.";
          homepage = "https://github.com/dsalwasser/kmpexp";
          license = pkgs.lib.licenses.mit;
          mainProgram = "kmpexp.py";
        };
      };
    }
  );
}
