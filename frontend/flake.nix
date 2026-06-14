{
  description = "Node project dev shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-26.05-darwin";

  outputs = { nixpkgs, ... }:
    let
      systems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];

      forAllSystems = nixpkgs.lib.genAttrs systems;

      mkNodeShell = nodePkgName: system:
        let
          pkgs = import nixpkgs { inherit system; };
          node = pkgs.${nodePkgName};
        in
        pkgs.mkShell {
          packages = [
            node
            pkgs.pnpm
          ];

          shellHook = ''
            export PATH="${node}/bin:${pkgs.pnpm}/bin:$PATH"
            export NPM_CONFIG_CACHE="$PWD/.npm-cache"
            export NPM_CONFIG_PREFIX="$PWD/.npm-global"
            export PATH="$NPM_CONFIG_PREFIX/bin:$PATH"

            mkdir -p "$NPM_CONFIG_CACHE" "$NPM_CONFIG_PREFIX" "$PWD/.corepack-bin"
            corepack enable --install-directory "$PWD/.corepack-bin" >/dev/null 2>&1 || true
            export PATH="$PWD/.corepack-bin:$PATH"

            printf 'node %s | npm %s | pnpm %s\n' \
              "$(node --version)" \
              "$(npm --version)" \
              "$(pnpm --version)"
          '';
        };
    in
    {
      devShells = forAllSystems (system: {
        default = mkNodeShell "nodejs_24" system;
        node22 = mkNodeShell "nodejs_22" system;
        node24 = mkNodeShell "nodejs_24" system;
        node26 = mkNodeShell "nodejs_26" system;
      });
    };
}
