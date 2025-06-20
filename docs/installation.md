# Installation

## Environment

This project uses uv for package management. uv is a fast Python package and project manager that supports Windows, MacOS, and Linux.

### Install uv

```shell
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or with pip
pip install uv
```

### Setup the Project

To install the environment, run the following commands from the project root directory:

```shell
# Create virtual environment
uv venv

# Activate the environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install the project in editable mode with all dependencies
uv pip install -e ".[dev,docs,build]"

# Or install from requirements files
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt
```

## Documentation
### Preview

Run
```
mkdocs serve
```
to start the live-reloading docs server.

The local website is run
on [http://127.0.0.1:8000/participation_certificate/](http://127.0.0.1:8000/pytube/)

MacOS-Error
>no library called "cairo-2" was found…

can be fixed with:
```
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
mkdocs serve
```
[See here for details](https://t.ly/MfX6u)

### Publishing

The documentation website is hosted at GitHub pages.

To deploy:
```
mkdocs gh-deploy
```

MacOS-Error
>no library called "cairo-2" was found…

can be fixed with:
```
export DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
mkdocs gh-deploy
```

before running `mkdocs gh-deploy` to install the cairo library.

## Versioning Schema

The versioning schema is `{major}.{minor}.{patch}[{release}{build}]` where the
latter part (release and build) is optional.

It is recommended to do `--dry-run` prior to your actual run.

```bash
# increase version identifier
bumpversion [major/minor/patch/release/build]  # --verbose --dry-run

# e.g.
bumpversion minor  # e.g. 0.5.1 --> 0.6.0
bumpversion minor --new-version 0.7.0  # e.g. 0.5.1 --> 0.7.0
```
