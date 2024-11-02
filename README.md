# uvn

[![PyPI version](https://img.shields.io/pypi/v/uvn)](https://pypi.org/project/uvn/)
[![License](https://img.shields.io/pypi/l/uvn)](https://opensource.org/licenses/MIT)
[![Python version](https://img.shields.io/pypi/pyversions/uvn)](https://pypi.org/project/uvn/)
[![Downloads](https://img.shields.io/pypi/dd/uvn)](https://pypi.org/project/uvn/)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](https://github.com/yourusername/uvn)

[`uvn`](https://github.com/xmodar/uvn) is a centralized Python virtual environment manager designed to work alongside [`uv`](https://astral.sh/uv), similar to [`conda`](https://conda.io) for general environment management.

## Highlights

- 🎯 **Centralized Environments**: Manage all environments from a single location.
- 🛠️ **`uv` Integration**: Complements `uv` to streamline virtual environment management.
- ⚡️ **Simple CLI Interface**: Easily list, create, activate, and remove environments with straightforward commands.
- 🗂️ **Export Options**: Quickly export configurations as `requirements.txt` or inline script metadata.
- 💾 **Cloning**: Easily clone environments to create new ones.
- 🚀 **Minimal Dependencies**: Designed for simplicity and speed.

## Installation

Install `uv` first.

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

> [!CAUTION]
> Do not install `uv` via `pip`; use the shell commands above.

Then, install `uvn` with the `cli` extra.

```bash
# From PyPI
uv tool install uvn[cli]

# From GitHub
uv tool install uvn[cli] @ git+https://github.com/xmodar/uvn
```

> [!IMPORTANT]
> Although `uvn` can be installed via `pip`, using `uv` is recommended for best integration.

Finally, install `uvna` for easy shell activation (e.g., in `~/.bashrc` for `bash`).

```bash
target="~/.bashrc"
uvna=$(cat <<'EOF'
uvna() {
    activate=$(uvn activate --quiet "$1")
    if [[ -n "$activate" ]]; then
        eval "$activate"
    else
        uvn list
        echo "Could not activate '"$1"'!" >&2
    fi
}
EOF
)
target="${target/#\~/$HOME}"
if [[ -f "$target" ]] && grep -q "uvna() {" "$target"; then
  sed -i "/^uvna() {/,/^}$/d" "$target"
fi
echo "$uvna" >> "$target"
source "$target"
```

> [!TIP]
> Install shell completion (optional):
> ```bash
> uvn --install-completion
> ```

## Usage

After installing `uvn`, manage virtual environments that are centralized and accessible from any directory, similar to `conda`.

### Quick Start

To begin, create and activate an environment.

```bash
uvn create test --python 3.12
uvna test
```

> [!WARNING]
> Currently, `uvn activate <ENV_NAME>` only outputs the command for activation. Use `uvna` or manually run the output command to activate.

The `list` and `remove` commands are simple.

```bash
# List environments with their sizes
uvn list --size

# Remove the 'test' environment
uvn remove test
```

To install packages, you can simply use `uv pip` in an activated environment.

```bash
uvna test
uv pip install # ...
```

The `export` command offers various options for exporting environment configurations.

```bash
# Print dependencies as in requirements.txt
uvn export test

# Export inline script metadata
uvn export test py --short --lower

# Generate a requirements.txt file
uvn export test requirements.txt

# Prepend inline script metadata (automatically detects ".py")
uvn export test script.py

# Clone the environment
uvn fork test test2
```

> [!TIP]
> Use `--help` with any command to see available options.

### Commands

Available commands in `uvn`:

```plaintext
Usage: uvn [OPTIONS] COMMAND [ARGS]...

╭─ Commands ──────────────────────────────────────────────────────────────────────────────────────────╮
  list       List all virtual environments.
  create     Create a virtual environment.
  remove     Remove a virtual environment.
  export     Export a virtual environment.
  fork       Copy a virtual environment.
  activate   Show environment command.
  version    Show uvn version.
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯

╭─ Options ───────────────────────────────────────────────────────────────────────────────────────────╮
 --install-completion Install completion for the current shell.
 --show-completion    Show completion for the current shell, to copy it or customize the installation.
 --help               Show this message and exit.
╰─────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

> [!TIP]
> Commands support prefixes (e.g., `uvn c` and `uvn cr` are short for `uvn create`).

> [!NOTE]
> The location of virtual environments can be set by changing the `UVN_DIR` environment variable. The default path is `~/.virtualenvs`.

## Contributing

Contributions are welcome! For suggestions or issues, please submit a pull request or open an issue on [GitHub](https://github.com/xmodar/uvn).
