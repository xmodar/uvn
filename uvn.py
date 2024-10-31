import os
import re
import math
import shutil
import tempfile
import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional, Union
from typing_extensions import Annotated

import typer
import shellingham
from rich.table import Table
from rich.console import Console
from rich.box import SIMPLE_HEAD

__version__ = "0.0.10"
__all__ = ["UVN_DIR", "app", "list_envs", "create", "remove", "export", "activate"]

UVN_DIR = Path(os.getenv("UVN_DIR", "~/.virtualenvs")).expanduser()
assert UVN_DIR.is_absolute(), f"Path is not absolute: UVN_DIR={str(UVN_DIR)}"


TPath = Union[str, Path]
TEnvName = Annotated[
    str,
    typer.Argument(
        help="The name of the virtual environment.",
        show_default=False,
    ),
]
TQuiet = Annotated[
    bool,
    typer.Option(
        "-q",
        "--quiet",
        help="Do not print any output.",
        show_default=False,
    ),
]


class PrefixTyperGroup(typer.core.TyperGroup):
    def get_command(self, ctx: typer.Context, cmd_name: str):
        matches = [c for c in self.commands if c.startswith(cmd_name)]
        if len(matches) == 1:
            cmd_name = matches[0]
        return super().get_command(ctx, cmd_name)


app = typer.Typer(
    cls=PrefixTyperGroup,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)
console = Console()


@app.callback(no_args_is_help=True)
def main() -> None:
    """uvn is conda for uv; a centralized Python virtual environment manager."""


def get_path_size(path: TPath) -> int:
    """Compute the size of the given directory"""
    paths = [path] if (path := Path(path)).is_file() else path.glob("**/*")
    return sum(f.stat().st_size for f in paths if f.is_file())


def format_data_size(num_bytes: int) -> str:
    return f"{num_bytes * 1024**-(p := round(math.log(num_bytes, 1024))):.2f} {' KMGTPEZY'[p]}B"


def get_version(python_path: TPath) -> str:
    return (
        subprocess.run([python_path, "--version"], stdout=subprocess.PIPE)
        .stdout[7:-1]
        .decode()
    )


def get_size(python_path: TPath) -> str:
    return format_data_size(get_path_size(Path(python_path).parent.parent))


@app.command("list")
def list_envs(
    size: Annotated[
        bool,
        typer.Option(
            "-s",
            "--size",
            help="Display the size of the environment.",
            show_default=False,
        ),
    ] = False,
) -> None:
    """List all available virtual environments."""
    python = "*/Scripts/python.exe" if os.name == "nt" else "*/bin/python"
    envs = sorted(
        (p.parts[-3], get_version(p), *([get_size(p)] if size else []), str(p))
        for p in UVN_DIR.glob(python)
    )
    table = Table(header_style="bold magenta", box=SIMPLE_HEAD)
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


class LinkMode(str, Enum):
    clone = "clone"
    copy = "copy"
    hardlink = "hardlink"
    symlink = "symlink"


@app.command(no_args_is_help=True)
def create(
    env_name: TEnvName,
    python: Annotated[
        Optional[str],
        typer.Option(
            "-p",
            "--python",
            help="The Python interpreter to use for the virtual environment.",
            envvar="UV_PYTHON",
            show_default=False,
        ),
    ] = None,
    prompt: Annotated[
        Optional[str],
        typer.Option(
            "-t",
            "--prompt",
            help="Provide an alternative prompt prefix for the virtual environment.",
            show_default=False,
        ),
    ] = None,
    link_mode: Annotated[
        Optional[LinkMode],
        typer.Option(
            "-l",
            "--linke-mode",
            help="The method to use when installing packages from the global cache.",
            envvar="UV_LINK_MODE",
            show_default=False,
        ),
    ] = None,
    quiet: TQuiet = False,
) -> None:
    """Create a virtual environment."""
    if (path := UVN_DIR / env_name).exists():
        env_name = f"[yellow]{env_name}[/yellow]"
        console.print(f"Environment {env_name} exists!", style="italic")
        return

    options = ["--no-project", "--no-config", "--python-preference", "only-managed"]
    if python:
        options.extend(["--python", python])
    if prompt:
        options.extend(["--prompt", prompt])
    if link_mode:
        options.extend(["--link-mode", link_mode])
    if quiet:
        options.append("--quiet")
    subprocess.run(["uv", "venv", *options, path])


@app.command(no_args_is_help=True)
def remove(env_name: TEnvName) -> None:
    """Remove a virtual environment."""
    path = UVN_DIR / env_name
    env_name = f"[yellow]{env_name}[/yellow]"
    if not path.exists():
        console.print(f"Environment {env_name} not found!", style="italic")
        return
    shutil.rmtree(path)
    console.print(f"Environment {env_name} was removed!", style="italic")


@app.command(no_args_is_help=True)
def activate(env_name: TEnvName, quiet: TQuiet = False) -> None:
    """Output the command to activate the specified environment."""
    if not env_name:
        if not quiet:
            console.print("Environment name is missing!", style="italic")
        return
    path = UVN_DIR / env_name
    if not path.exists():
        if not quiet:
            env_name = f"[yellow]{env_name}[/yellow]"
            console.print(f"Environment {env_name} not found!", style="italic")
        return
    try:
        # https://docs.python.org/3/library/venv.html#how-venvs-work
        shell, _ = shellingham.detect_shell()
        command = {
            "bash": "source {}/bin/activate",
            "zsh": "source {}/bin/activate",
            "fish": "source {}/bin/activate.fish",
            "csh": "source {}/bin/activate.csh",
            "tcsh": "source {}/bin/activate.csh",
            "nu": "source {}/bin/activate.nu",
            "pwsh": "{}/bin/Activate.ps1",
            "powershell": "{}/Scripts/Activate.ps1",
            "cmd": "{}/Scripts/activate.bat",
        }[shell].format(str(path))
        console.print(command, highlight=False)
    except Exception as exception:
        if not quiet:
            raise exception


def run_in_env(env_name: TEnvName, *args, **kwargs):
    path = UVN_DIR / env_name
    if not path.exists():
        env_name = f"[yellow]{env_name}[/yellow]"
        console.print(f"Environment {env_name} not found!", style="italic")
        return
    kwargs.setdefault("env", os.environ)
    kwargs["env"] = kwargs["env"].copy()
    kwargs["env"]["VIRTUAL_ENV"] = str(path)
    return subprocess.run(*args, **kwargs)


def get_dependencies(env_name: TEnvName, short: bool = True) -> "str | None":
    options = ["tree", "-d", "0"] if short else ["freeze"]
    res = run_in_env(
        env_name,
        ["uv", "pip"] + options,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if res is None:
        return
    version = res.stderr.split(" ", 3)[-2]
    dep = f"# python=={version}\n{res.stdout}"
    if short:
        dep = dep.replace(" v", "==")
    return dep.strip()


def to_inline_script(dependencies: str) -> str:
    version, dep = dependencies.split("\n", 1)
    dep = dep.replace("==", ">=")
    dep = "\n".join(f'#     "{d}",' for d in dep.splitlines())
    dep = f"# dependencies = [\n{dep}\n# ]\n" if dep else ""

    _, version = version.split("==")
    major, minor, _ = version.split(".", 2)
    limit = f"{major}.{int(minor) + 1}"
    python = f'# requires-python = ">={version},<{limit}"\n'

    return f"#!/usr/bin/env -S uv run\n# /// script\n{python}{dep}# ///\n"


def remove_inline_script(text: str) -> str:
    return re.sub("^(?:#!.*\n)?# /// script\n(# .*\n)*?# ///\n", "", text)


def clone(env_name: TEnvName, new_env: str) -> bool:
    path = UVN_DIR / new_env
    if path.exists():
        new_env = f"[yellow]{new_env}[/yellow]"
        console.print(f"Environment {new_env} exists!", style="italic")
        return False

    dep = get_dependencies(env_name, short=False)
    if dep is None:
        return False
    version, dep = dep.split("\n", 1)
    _, version = version.split("==")

    res = subprocess.run(["uv", "venv", "-p", version, "--no-project", path])
    if res.returncode != 0:
        return False

    if dep:
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as file:
            file.write(dep)
            file.flush()
            run_in_env(new_env, ["uv", "pip", "install", "-r", file.name])
    return True


@app.command(no_args_is_help=True)
def export(
    env_name: TEnvName,
    to: Annotated[
        Path,
        typer.Option(
            "-t",
            "--to",
            help="Export to (*.txt | *.py | <NEW_ENV_NAME>)",
            show_default=False,
        ),
    ] = None,
    script: Annotated[
        bool,
        typer.Option(
            "-s",
            "--script",
            help="Export as an inline script metadata.",
            show_default=False,
        ),
    ] = False,
    top_level: Annotated[
        bool,
        typer.Option(
            "-l",
            "--top-level",
            help="Export only the top-level dependencies (depth = 0).",
            show_default=False,
        ),
    ] = False,
) -> None:
    """Export or clone a virtual environment."""
    if to:
        if str(to) == to.stem:
            clone(env_name, new_env=to.stem)
            return
        elif to.suffix == ".txt":
            script = False
        elif to.suffix == ".py":
            script = True
        else:
            console.print(f"Invalid target: [blue]{to}[/blue]", style="italic")
            return

    dep = get_dependencies(env_name, top_level)
    if dep is None:
        return
    if script:
        dep = to_inline_script(dep)
    else:
        dep += "\n"

    if to:
        to = to.expanduser()
        if to.suffix == ".py" and to.exists():
            dep += remove_inline_script(to.read_text())
        else:
            to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(dep)
        console.print(f"File [blue]{to}[/blue] updated!")
    else:
        console.print(dep, end="", highlight=False)
