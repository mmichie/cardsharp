{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python314
    pkgs.uv
  ];

  env = {
    UV_PYTHON_PREFERENCE = "only-system";
    UV_PYTHON = "${pkgs.python314}/bin/python3.14";
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
  };

  shellHook = ''
    echo "cardsharp dev shell — Python $(python3.14 --version 2>&1 | cut -d' ' -f2), uv $(uv --version 2>&1 | cut -d' ' -f2)"
    uv sync --quiet 2>/dev/null
  '';
}
