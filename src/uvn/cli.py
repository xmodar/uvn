import re
from pathlib import Path
from typing import Optional

try:
    import typer
    import shellingham
    from rich.live import Live
    from rich.table import Table
    from rich.console import Console
    from rich.box import SIMPLE_HEAD
    from typer.core import TyperGroup
    from typing_extensions import Annotated
except ImportError as e:
    raise SystemExit(
        f"Required package missing: `{e.name}`. "
        "Did you forget to install the `uvn[cli]` extra?"
    ) from e

from . import __version__
from .core import UVN


class PrefixTyperGroup(TyperGroup):
    def list_commands(self, ctx: typer.Context):
        return self.commands

    def get_command(self, ctx: typer.Context, cmd_name: str):
        matches = [c for c in self.commands if c.startswith(cmd_name)]
        if len(matches) == 1:
            cmd_name = matches[0]
        return super().get_command(ctx, cmd_name)


console = Console()
app = typer.Typer(
    cls=PrefixTyperGroup,
    context_settings={
        "help_option_names": ["-h", "--help"],
    },
)


def echo(message: str):
    console.print(re.sub("`(.*?)`", "[yellow]\\1[/yellow]", message), style="italic")


@app.callback(no_args_is_help=True)
def main():
    """uvn is conda for uv; a centralized Python virtual environment manager."""


Directory = Annotated[
    Path,
    typer.Option(
        "-d",
        "--directory",
        help="Root directory for virtual environments.",
        envvar="UVN_DIR",
    ),
]


@app.command("list")
def list_envs(
    size: Annotated[
        Optional[bool],
        typer.Option(
            "-s",
            "--size",
            help="Show the sizes of the environments.",
        ),
    ] = None,
    full_version: Annotated[
        Optional[bool],
        typer.Option(
            "-f",
            "--full-version",
            help="Show the full versions of the environments.",
        ),
    ] = None,
    directory: Directory = UVN.DIR,
):
    """List all virtual environments."""
    envs = sorted(UVN.list(root=directory))
    if envs:
        table = Table(header_style="bold magenta", box=SIMPLE_HEAD)
        table.add_column("Name", style="yellow")
        table.add_column("Version", style="green")
        if size:
            table.add_column("Size", style="white", justify="right")
        table.add_column("Path", style="blue", no_wrap=True)
        with Live(table, console=console) as live:
            for env in envs:
                version = env.full_version if full_version else env.version_segment
                row = [env.name, version, str(env.path)]
                if size:
                    row.insert(2, env.readable_size)
                table.add_row(*row)
                live.update(table)
    echo(f"Found {len(envs)} environments.")


EnvName = Annotated[
    str,
    typer.Argument(
        help="The name of the virtual environment.",
        show_default=False,
    ),
]
LinkMode = Annotated[
    Optional[UVN.LinkMode],
    typer.Option(
        "-l",
        "--linke-mode",
        help="The method to use when installing packages from the global cache.",
        envvar="UV_LINK_MODE",
        show_default=False,
    ),
]
Quiet = Annotated[
    Optional[bool],
    typer.Option(
        "-q",
        "--quiet",
        help="Do not print any output.",
    ),
]


def handle_local(env_name: str, directory: Path) -> "tuple[str, Path]":
    if env_name == ".":
        env_name = ".venv"
        if directory == UVN.DIR:
            directory = Path(".")
    return env_name, directory


@app.command(no_args_is_help=True)
def create(
    env_name: EnvName,
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
    link_mode: LinkMode = None,
    directory: Directory = UVN.DIR,
    quiet: Quiet = None,
):
    """Create a virtual environment."""
    env_name, directory = handle_local(env_name, directory)
    try:
        UVN.create(
            env_name,
            root=directory,
            python=python,
            link_mode=link_mode,
            quiet=bool(quiet),
        )
    except UVN.ExistsError as e:
        echo(e.args[0])
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def remove(
    env_name: EnvName,
    force: Annotated[
        Optional[bool],
        typer.Option(
            "-f",
            "--force",
            help="Delete environment path even if corrupted.",
        ),
    ] = None,
    directory: Directory = UVN.DIR,
):
    """Remove a virtual environment."""
    env_name, directory = handle_local(env_name, directory)
    removed = corrupted = False
    try:
        removed = UVN.remove(env_name, root=directory, strict=not force)
    except UVN.MissingError:
        pass
    except UVN.CorruptedError:
        corrupted = True
    echo(f"Environment `{env_name}` was{'' if removed else ' not'} removed!")
    if corrupted:
        echo("It appears to be corrupted, use --force to remove it anyways.")
    if not (removed or force):
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def export(
    env_name: EnvName,
    target: Annotated[
        Path,
        typer.Argument(help="Path to file or one of [txt|toml|py|lock]."),
    ] = Path("txt"),
    short: Annotated[
        bool,
        typer.Option(
            "-s",
            "--short",
            help="Export only top-level packages.",
        ),
    ] = False,
    lower: Annotated[
        bool,
        typer.Option(
            "-l",
            "--lower",
            help="Use '>=' instead of '==' for version specifiers.",
        ),
    ] = False,
    directory: Directory = UVN.DIR,
    verbose: Annotated[
        Optional[bool],
        typer.Option(
            "-v",
            "--verbose",
            help="Show progress when generating lock file.",
        ),
    ] = None,
):
    """Export a virtual environment."""
    env_name, directory = handle_local(env_name, directory)
    try:
        env = UVN(directory / env_name)
    except UVN.Error as e:
        echo(e.args[0])
        raise typer.Exit(1)
    method = str(target)
    if method == "txt":
        dep = env.get_requirements(full=not short, exact=not lower)
    elif method == "toml":
        dep = env.get_pyproject(full=not short, exact=not lower)
    elif method == "py":
        dep = env.get_script_metadata(full=not short, exact=not lower)
    elif method == "lock":
        dep = env.get_lock(quiet=not verbose)
    else:
        env.export(target, full=not short, exact=not lower, quiet=not verbose)
        return
    console.print(dep, highlight=False)


@app.command(no_args_is_help=True)
def fork(
    env_name: EnvName,
    new_name: Annotated[
        str,
        typer.Argument(
            help="The name of the new environment.",
            show_default=False,
        ),
    ],
    link_mode: LinkMode = None,
    directory: Directory = UVN.DIR,
    new_directory: Annotated[
        Optional[Path],
        typer.Option(
            "-n",
            "--new-directory",
            help="Root directory for the new environment (defaults to --directory).",
            show_default=False,
        ),
    ] = None,
    quiet: Quiet = None,
):
    """Copy a virtual environment."""
    if new_directory is None:
        new_directory = directory
    env_name, directory = handle_local(env_name, directory)
    try:
        env = UVN(directory / env_name)
    except UVN.Error:
        echo(f"Environment `{env_name}` not found!")
        raise typer.Exit(1)
    try:
        env.fork(
            new_name,
            root=new_directory,
            link_mode=link_mode,
            quiet=bool(quiet),
        )
    except UVN.Error as e:
        echo(e.args[0])
        raise typer.Exit(1)


@app.command(no_args_is_help=True)
def activate(
    env_name: EnvName,
    shell: Annotated[
        Optional[UVN.Shell],
        typer.Option(
            "-s",
            "--shell",
            help="Shell name (auto-detected by default).",
            show_default=False,
        ),
    ] = None,
    directory: Directory = UVN.DIR,
    quiet: Quiet = None,
):
    """Show environment command."""
    env_name, directory = handle_local(env_name, directory)
    if shell is None:
        name, _ = shellingham.detect_shell()
        shells = [s.value for s in UVN.Shell]
        if name not in shells:
            if not quiet:
                echo(f"Detected unknown shell `{name}` not in {shells}")
            raise typer.Exit(1)
        shell = UVN.Shell[name.upper()]
    try:
        command = UVN(directory / env_name).get_activate(shell)
        console.print(command, highlight=False)
    except UVN.Error:
        if not quiet:
            echo(f"Environment `{env_name}` not found!")


@app.command()
def version():
    """Show uvn version."""
    console.print(__version__, highlight=False)
