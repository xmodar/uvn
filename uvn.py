import os
import re
import math
import shutil
import subprocess
from enum import Enum
from pathlib import Path
from functools import wraps
from typing_extensions import Annotated
from inspect import Signature, Parameter

import typer
import shellingham
from click.core import Context
from rich.table import Table
from rich.console import Console
from rich.box import SIMPLE_HEAD

__version__ = "0.0.6"

UVN_DIR = Path(os.getenv("UVN_DIR", "~/.virtualenvs")).expanduser()
assert UVN_DIR.is_absolute(), f"Path is not absolute: UVN_DIR={str(UVN_DIR)}"


class PrefixTyperGroup(typer.core.TyperGroup):
    def get_command(self, ctx: Context, cmd_name: str):
        matches = [c for c in self.commands if c.startswith(cmd_name)]
        if len(matches) == 1:
            cmd_name = matches[0]
        return super().get_command(ctx, cmd_name)


app = typer.Typer(cls=PrefixTyperGroup)
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


def parse_venv_options():
    msg = subprocess.run(["uv", "venv", "-h"], stdout=subprocess.PIPE).stdout.decode()
    msg = re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", msg)  # remove ANSI colors
    msg = re.sub(r"\n  -\w,", "\n     ", msg)  # remove short names
    msg = re.sub(r"\n {10,}", " ", msg)  # rejoin lines
    pattern = re.compile(
        r" {6}--(?P<name>[a-z\-]+)\.*"
        r"(?: ?<(?P<var>[A-Z_]+)>)?\s*"
        r"(?: ?\(Deprecated: (?P<deprecated>[^\)]*)\))?"
        r"(?P<help>[^\[\n]+)"
        r"(?: ?\[default: (?P<default>[^\]]+)\])?"
        r"(?: ?\[env: (?P<env>[^\]=]+)=?\])?"
        r"(?: ?\[possible values: (?P<choices>[^\]]+)\])?"
    )
    return {
        opt["name"]: (
            Enum(
                "".join(x.title() for x in opt["name"].split("-")),
                {choice: choice for choice in opt["choices"]},
                type=str,
            )
            if opt["choices"]
            else opt["type"],
            typer.Option(
                "--" + opt["name"],
                envvar=opt["env"],
                help=opt["help"],
                show_default=bool(opt["default"]),
            ),
            opt["default"] if opt["type"] is str else False,
        )
        for m in pattern.finditer(msg)
        if not (
            opt := {
                "name": m.group("name"),
                "type": str if m.group("var") else bool,
                "deprecated": m.group("deprecated"),
                "help": m.group("help").strip(),
                "default": m.group("default"),
                "env": m.group("env"),
                "choices": c.split(", ") if (c := m.group("choices")) else [],
            }
        )["deprecated"]
        and opt["name"] != "help"
    }


def wrap_create(func):
    sig = Signature(
        [Parameter("env_name", Parameter.POSITIONAL_OR_KEYWORD, annotation=str)]
        + [
            Parameter(
                name.replace("-", "_"),
                Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=Annotated[type_, option],
            )
            for name, (type_, option, default) in parse_venv_options().items()
        ]
    )

    @wraps(func)
    def wrapper(*args, **kwargs):
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        return func(**bound_args.arguments)

    wrapper.__signature__ = sig
    return wrapper


@app.command(no_args_is_help=True)
@wrap_create
def create(env_name: str, **kwargs) -> None:
    """Create a new virtual environment."""
    path = UVN_DIR / env_name
    if path.exists():
        env_name = f"[yellow]{env_name}[/yellow]"
        console.print(f"Environment {env_name} exists!", style="italic")
        return
    options = []
    for k, v in kwargs.items():
        if v not in (None, False):
            options.append(f"--{k}")
            if v is not True:
                options.append(v)
    subprocess.run(["uv", "venv", *options, path])


@app.command(no_args_is_help=True)
def remove(env_name: str) -> None:
    """Remove a virtual environment."""
    path = UVN_DIR / env_name
    env_name = f"[yellow]{env_name}[/yellow]"
    if not path.exists():
        console.print(f"Environment {env_name} not found!", style="italic")
        return
    shutil.rmtree(path)
    console.print(f"Environment {env_name} was removed!", style="italic")


@app.command(no_args_is_help=True)
def activate(env_name: str) -> None:
    """Print the activation command for the given environment."""
    path = UVN_DIR / env_name
    if not path.exists():
        env_name = f"[yellow]{env_name}[/yellow]"
        console.print(f"Environment {env_name} not found!", style="italic")
        return
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


@app.command(no_args_is_help=True)
def export(env_name: str, script: bool = False, to: Path = None) -> None:
    """Export a virtual environment requirements or as inline script metadata."""
    path = UVN_DIR / env_name
    if not path.exists():
        env_name = f"[yellow]{env_name}[/yellow]"
        console.print(f"Environment {env_name} not found!", style="italic")
        return
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(path)
    if script or to and to.suffix == ".py":
        res = subprocess.run(
            ["uv", "pip", "tree", "-d", "0"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        version = res.stderr.split(" ", 3)[-2]
        dep = res.stdout.replace(" v", ">=").strip()
        req = "#!/usr/bin/env -S uv run"
        req += "\n# /// script"
        major, minor, _ = version.split(".", 2)
        limit = f"{major}.{int(minor) + 1}"
        req += f'\n# requires-python = ">={version},<{limit}"'
        if dep:
            req += "\n# dependencies = ["
            for line in dep.splitlines():
                req += f'\n#     "{line}",'
            req += "\n# ]"
        req += "\n# ///\n"
    else:
        res = subprocess.run(
            ["uv", "pip", "freeze"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        version = res.stderr.split(" ", 3)[-2]
        req = f"# python=={version}\n{res.stdout}"
    if to:
        to = to.expanduser()
        if to.suffix == ".py" and to.exists():
            text = to.read_text()
            text = re.sub("^(?:#!.*\n)?# /// script\n(# .*\n)*?# ///\n", "", text)
            req += text
        else:
            to.parent.mkdir(parents=True, exist_ok=True)
        to.write_text(req)
        console.print(f"File [blue]{to}[/blue] updated!")
    else:
        console.print(req, end="", highlight=False)
