# Releasing

Two packages publish to PyPI independently, each via GitHub Actions and
PyPI Trusted Publishing (OIDC -- no API tokens are stored anywhere):

| Package          | Tag prefix  | Wheels                          | Workflow                |
| ---------------- | ----------- | ------------------------------- | ----------------------- |
| `cardsharp`      | `v*`        | one `py3-none-any` + sdist      | `release.yml`           |
| `cardsharp-core` | `core-v*`   | per-platform abi3 wheels + sdist | `release-core.yml`      |

`cardsharp` is the pure-Python package; `cardsharp-core` is the Rust fast
core. They version on separate lines (`cardsharp` is 0.x, `cardsharp-core`
starts at 0.1.0). `cardsharp[fast]` depends on `cardsharp-core>=0.1.0`, so
the core must be on PyPI for the extra to resolve.

The Rust core is built with PyO3 `abi3-py312`: a single wheel per platform
serves every CPython >= 3.12, so the build matrix is platforms only
(manylinux + musllinux x86_64/aarch64, macOS x86_64/aarch64, Windows x64).
Free-threaded and 32-bit/exotic targets are intentionally omitted; those
users build from the sdist.

## One-time setup (PyPI side, maintainer)

Trusted Publishing must be configured once per project on PyPI before the
first publish. `cardsharp` already exists on PyPI; `cardsharp-core` does
not yet, so it is registered as a *pending* publisher (PyPI creates the
project on the first successful upload).

For **each** project, at <https://pypi.org/manage/account/publishing/>
(or the project's Settings -> Publishing for an existing project), add a
GitHub Actions trusted publisher:

| Field             | `cardsharp`         | `cardsharp-core`         |
| ----------------- | ------------------- | ------------------------ |
| PyPI project name | `cardsharp`         | `cardsharp-core`         |
| Owner             | `mmichie`           | `mmichie`                |
| Repository        | `cardsharp`         | `cardsharp`              |
| Workflow filename | `release.yml`       | `release-core.yml`       |
| Environment       | `pypi`              | `pypi`                   |

Then, once per repository, create a GitHub Environment named `pypi`
(Settings -> Environments -> New environment). Add yourself as a required
reviewer if you want a manual approval gate before every upload --
recommended: the workflow builds and waits, you click to publish.

No secrets, no tokens. The `id-token: write` permission on the publish
job lets GitHub mint a short-lived OIDC credential PyPI verifies against
the trusted-publisher config above.

## Cutting a release

Both workflows also run on `workflow_dispatch`, which builds the wheels
and uploads them as run artifacts but never publishes -- use that to
dry-run a build before tagging.

### cardsharp (pure Python)

1. Bump `version` in `pyproject.toml` and add a `CHANGELOG.md` entry.
2. Commit, then tag and push:
   ```bash
   git tag -a v0.8.0 -m "Release version 0.8.0"
   git push --follow-tags
   ```
3. `release.yml` builds the sdist + wheel, asserts the tag matches the
   `pyproject.toml` version, and waits at the `pypi` environment.
4. Approve the environment in the Actions run to publish.

### cardsharp-core (Rust)

1. Bump `version` in **both** `crates/cardsharp-core/Cargo.toml` and
   `crates/cardsharp-core/pyproject.toml` (keep them equal).
2. If the core's API grew in a way the facade now requires, raise the
   floor pin in the root `pyproject.toml` `fast` extra to match.
3. Commit, then tag and push:
   ```bash
   git tag -a core-v0.1.0 -m "cardsharp-core 0.1.0"
   git push --follow-tags
   ```
4. `release-core.yml` builds every platform wheel + sdist, smoke-imports
   each natively built wheel, and waits at the `pypi` environment.
5. Approve to publish.

## The Rust crate: `publish = false`, pin by tag

`cardsharp-core` is a Cargo crate as well as a Python package. It builds
as a cdylib (the extension module) and as an rlib, so a Rust project can
depend on the round engine directly, with PyO3 left out entirely:

```toml
[dependencies]
cardsharp-core = { git = "https://github.com/mmichie/cardsharp", tag = "core-v0.1.0", default-features = false }
```

`default-features = false` is belt and braces -- there are no default
features -- but it states the intent: the `python` feature is what
compiles the PyO3 boundary, only maturin turns it on, and a Rust
consumer never wants libpython on its link line. `serde` is the other
one worth knowing about: it adds derives to `Rules`, the round records
and the session step/answer types.

**`publish = false` stays.** The crate is not on crates.io and there is
no plan to put it there; the same `core-v*` tags the wheels are cut from
are the Rust release line, so pinning by tag and pinning by wheel name
the same version. That has one consequence a downstream should know:

- **Pin by tag, not by branch.** `master` moves, and a `git` dependency
  with no `tag`/`rev` re-resolves on every `cargo update`.
- **A `core-v*` tag is a Rust release too.** Whoever cuts one owns the
  Rust API in it, so a breaking change to `Rules`, `machine::Answer` /
  `machine::Step`, or `Rules::digest`'s value belongs in the same
  `CHANGELOG.md` entry as the Python-visible changes. `digest` is the
  sharp one: adding a rule field changes every digest, on purpose, and a
  downstream that stored digests has to be told.
- **Versioning is the wheel's.** There is no separate Rust version line
  to bump; step 1 above (keeping `Cargo.toml` and `pyproject.toml`
  equal) is what a downstream reads off the tag.

## Verifying an install from PyPI

```bash
pip install "cardsharp[fast]"            # pulls cardsharp + cardsharp-core wheel
python -c "import cardsharp_core as c; print(c.engine_version())"
```

Without `[fast]`, `cardsharp` installs pure-Python. NOTE: as of the
single-engine retirement (beads-i2s.6), the pure-Python round engine is
deprecated and slated for deletion; after that lands, `[fast]` (or a
local Rust build) is required for simulation and interactive play.
