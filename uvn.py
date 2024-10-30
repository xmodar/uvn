import os
import math
import subprocess
from pathlib import Path

import typer
from rich.table import Table
from rich.console import Console
from rich.box import SIMPLE_HEAD

__version__ = "0.0.1"

UVN_DIR = Path(os.getenv("UVN_DIR", "~/.virtualenvs")).expanduser()
assert (
    UVN_DIR.is_absolute()
), f"Environments path must be absolute: UVN_DIR={str(UVN_DIR)}"


app = typer.Typer()
console = Console()


@app.callback(no_args_is_help=True)
def main() -> None:
    """uvn is conda for uv; a centralized Python virtual environment manager."""


def get_path_size(path: "str | Path") -> int:
    """Compute the size of the given directory"""
    paths = [path] if (path := Path(path)).is_file() else path.glob("**/*")
    return sum(f.stat().st_size for f in paths if f.is_file())


def format_data_size(num_bytes: int) -> str:
    power = math.floor(math.log(num_bytes, 1024))
    prefix = "KMGTPEZY"[power - 1] if power > 0 else ""
    return f"{num_bytes * 1024**-power:.2f} {prefix}B"


def get_version(python_path: "str | Path") -> str:
    return (
        subprocess.run([python_path, "--version"], stdout=subprocess.PIPE)
        .stdout[7:-1]
        .decode()
    )


def get_size(python_path: "str | Path") -> str:
    return format_data_size(get_path_size(Path(python_path).parent.parent))


@app.command("list")
def list_envs(size: bool = False, head: bool = True) -> None:
    """List all available virtual environments."""
    python = "*/Scripts/python.exe" if os.name == "nt" else "*/bin/python"
    envs = sorted(
        (p.parts[-3], get_version(p), *([get_size(p)] if size else []), str(p))
        for p in UVN_DIR.glob(python)
    )
    head = envs and head
    table = Table(header_style="bold magenta", box=SIMPLE_HEAD, show_header=head)
    table.add_column("Name", style="yellow")
    table.add_column("Version", style="green")
    if size:
        table.add_column("Size", style="white")
    table.add_column("Path", style="blue", no_wrap=True)
    for row in envs:
        table.add_row(*row)
    if envs:
        console.print(table)
    console.print(f"Found {len(envs)} environments.", style="italic")
