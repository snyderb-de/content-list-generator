# Node Project Template

This template gives a project its own Nix-managed Node toolchain.

```sh
direnv allow
```

Defaults:

- `default` / `node24`: Node 24 LTS
- `node22`: Node 22
- `node26`: Node 26 current

Use a non-default shell explicitly:

```sh
nix develop .#node22
nix develop .#node26
```

To make a project permanently use a different shell with direnv, edit `.envrc`:

```sh
use flake .#node22
```

Project-local npm locations:

- npm cache: `.npm-cache`
- npm global prefix: `.npm-global`
- corepack shims: `.corepack-bin`
