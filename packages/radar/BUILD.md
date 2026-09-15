# Build Session Receipt from source

The CLI and native Mac shell are in this repository. The hosted Forkit website,
accounts and team services are separate. Build commands below do not publish.

Use Python 3.11 on Apple Silicon Mac, or Python 3.12 on Ubuntu ARM64. Run from the
repository root in an isolated virtual environment:

```sh
python -m pip install --require-hashes -r requirements/radar-dev.lock
python -m build --wheel --no-isolation --outdir output/dist .
python -m build --wheel --no-isolation --outdir output/dist packages/radar
python -m pip install --no-deps output/dist/*.whl
PYTHONPATH=.:packages/radar/src python -m pytest --import-mode=importlib tests packages/radar/tests scripts/tests -q
python -m pip download --only-binary=:all: --require-hashes -r requirements/radar-runtime.lock --dest output/wheelhouse
python scripts/build_radar_bundle.py --project-wheels output/dist --wheelhouse output/wheelhouse --output output/session-receipt-cli.zip
python scripts/check_radar_public_bundle.py output/session-receipt-cli.zip --output output/install-check.json
```

Native builds need Apple command-line developer tools and an Apple Silicon Mac.
Obtain these exact upstream archives; the builder checks their hashes:

- [CPython 3.11.16 standalone archive](https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.11.16%2B20260901-aarch64-apple-darwin-install_only_stripped.tar.gz), SHA-256 `768f05cf200273bbdda9a5955a5a6892a4b22f2a0b1e4b0a9160f5c7fce86816`.
- [Git 2.55.0 source](https://www.kernel.org/pub/software/scm/git/git-2.55.0.tar.xz), SHA-256 `457fdb04dc8728e007d4688695e6912e6f680727920f2a40bf11eacc17505357`.

```sh
python scripts/build_radar_macos.py \
  --runtime-archive /absolute/path/to/python.tar.gz \
  --git-archive /absolute/path/to/git.tar.xz \
  --project-wheels output/dist --wheelhouse output/wheelhouse \
  --output 'output/Forkit Session Receipt.app' --work-dir output/native-build
```

Choose output/work paths that do not already exist. The native build is ad-hoc
signed for developer evaluation; it is not Developer ID signed or notarized.
Dependency notices are retained. Application-file byte equality can be checked
against the distributed wheels; archive timestamps/signatures/metadata are not
claimed to be bit-for-bit reproducible. See [Mac limitations](MACOS.md).
