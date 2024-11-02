import os
import re
import math
import shutil
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional
from functools import total_ordering
from subprocess import CompletedProcess, run, PIPE, DEVNULL


@total_ordering
class UVN:
    """Python virtual environment managed by uv."""

    class Error(Exception):
        """UVN environment error."""

    class UVError(ChildProcessError, Error):
        """UV process failed to execute command."""

    class MissingError(FileNotFoundError, Error):
        """Environment is missing."""

    class CorruptedError(ChildProcessError, Error):
        """Environment is corrupted."""

    class ExistsError(FileExistsError, Error):
        """Environment exists."""

    class FeatureError(NotImplementedError, Error):
        """Feature is not implemented."""

    DIR = Path(os.getenv("UVN_DIR", "~/.virtualenvs")).expanduser().absolute()

    def __init__(self, path: Path) -> None:
        self.path: Path = path.expanduser().absolute()
        if not self.python.exists():
            raise self.MissingError(f"Python interpreter: {self.python}")
        cmd = "import platform as p; print(p.python_version(), end='')"
        res = run([self.python, "-c", cmd], stdout=PIPE, stderr=PIPE, text=True)
        if res.returncode != 0:
            raise self.CorruptedError(f"Python version ({self.python}):\n{res.stderr}")
        self.version: str = res.stdout

    def __eq__(self, other: "UVN") -> bool:
        return self.path == other.path

    def __lt__(self, other: "UVN") -> bool:
        return self.path.stat().st_ctime < other.path.stat().st_ctime

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self.path}')"

    @property
    def python(self) -> Path:
        """Path to the python interpreter for this environment."""
        python = "Scripts/python.exe" if os.name == "nt" else "bin/python"
        return self.path / python

    @property
    def name(self) -> str:
        """Virtual environment name."""
        return self.path.name

    @property
    def size(self) -> int:
        """Size in bytes of the virtual environment."""
        return sum(f.stat().st_size for f in self.path.glob("**/*") if f.is_file())

    @property
    def readable_size(self) -> str:
        """Human-readable size of the virtual environment."""
        size = self.size
        power = int(math.log(size, 1000))
        return f"{size * 1000**-power:.2f} {' KMGTPEZY'[power]}B"

    @property
    def full_version(self) -> str:
        """Fully qualified python version (impl-ver-sys-arch-libc)."""
        return Path(os.readlink(self.python)).parts[-3]

    @property
    def implementation(self) -> str:
        """Python implementation name."""
        return self.full_version.split("-", 1)[0]

    @property
    def version_segment(self) -> str:
        """Python version that might also include a local segment."""
        return self.full_version.split("-", 2)[1]

    @property
    def is_free_threaded(self) -> bool:
        """Whether the python interpreter is GIL free."""
        return "freethreaded" in self.full_version

    @property
    def system(self) -> str:
        """System name."""
        return self.full_version.split("-", 3)[2]

    @property
    def machine(self) -> str:
        """Machine architecture."""
        return self.full_version.rsplit("-", 2)[1]

    @property
    def libc(self) -> str:
        """C library type."""
        return self.full_version.rsplit("-", 1)[1]

    def run(self, *args, **kwargs) -> CompletedProcess:
        """Run some command in the environment."""
        kwargs["env"] = kwargs.setdefault("env", os.environ).copy()
        kwargs["env"]["VIRTUAL_ENV"] = str(self.path)
        return run(*args, **kwargs)

    class Shell(str, Enum):
        BASH = "bash"
        ZSH = "zsh"
        FISH = "fish"
        CSH = "csh"
        TCSH = "tcsh"
        NU = "nu"
        PWSH = "pwsh"
        POWERSHELL = "powershell"
        CMD = "cmd"

    def get_activate(self, shell: Shell) -> str:
        """Get the command to activate the environment on the given shell."""
        return {
            self.Shell.BASH: "source {}/bin/activate",
            self.Shell.ZSH: "source {}/bin/activate",
            self.Shell.FISH: "source {}/bin/activate.fish",
            self.Shell.CSH: "source {}/bin/activate.csh",
            self.Shell.TCSH: "source {}/bin/activate.csh",
            self.Shell.NU: "source {}/bin/activate.nu",
            self.Shell.PWSH: "{}/bin/Activate.ps1",
            self.Shell.POWERSHELL: "{}/Scripts/Activate.ps1",
            self.Shell.CMD: "{}/Scripts/activate.bat",
        }[shell].format(self.path)

    def get_requirements(self, *, full: bool = True, exact: bool = True) -> str:
        """Get the requirements of the virtual environment."""
        opt = ["freeze"] if full else ["tree", "-d", "0"]
        res = self.run(["uv", "pip"] + opt, stdout=PIPE, stderr=DEVNULL, text=True)
        if res.returncode != 0:
            raise self.UVError(f"Could not run pip in `{self.name}`!")
        req = res.stdout
        if not full:
            req = req.replace(" v", "==" if exact else ">=")
        elif not exact:
            req = req.replace("==", ">=")
        return f"# {self.full_version}\n{req}".strip()

    def get_dependencies(self, *, full: bool = False, exact: bool = False) -> str:
        """Get the dependencies of the virtual environment."""
        req = self.get_requirements(full=full, exact=exact).splitlines()
        dep = "\n".join(f'    "{r}",' for r in req[1:])
        dep = f"\ndependencies = [\n{dep}\n]" if dep else ""
        ver = f"=={self.version_segment}" if exact else f">={self.version}"
        return f'requires-python = "{ver}" {req[0]}{dep}'

    def get_script_metadata(
        self, text: str = "", *, full: bool = False, exact: bool = True
    ) -> str:
        """Add the inline script metadata to the given script text."""
        if text:
            text = re.sub("^(?:#!.*\n)?# /// script\n(# .*\n)*?# ///\n", "\n", text)
        dep = self.get_dependencies(full=full, exact=exact).replace("\n", "\n# ")
        return f"#!/usr/bin/env -S uv run\n# /// script\n# {dep}\n# ///{text}"

    def get_pyproject(
        self, text: str = "", *, full: bool = False, exact: bool = True
    ) -> str:
        """Add the virtual environment dependencies to the given TOML text."""
        if text:
            raise self.FeatureError("Cannot yet update TOML files.")
        text = f'[project]\nname = "{self.name}"\ndynamic = ["version"]\n'
        return text + self.get_dependencies(full=full, exact=exact)

    def get_lock(self, *, quiet: bool = True) -> str:
        """Get the uv.lock file of the virtual environment."""
        with tempfile.TemporaryDirectory() as directory:
            pyproject = self.get_pyproject(full=True, exact=True)
            (Path(directory) / "pyproject.toml").write_text(pyproject)
            opt = ["--directory", directory]
            if quiet:
                opt.append("--quiet")
            res = run(["uv", "lock"] + opt)
            if res.returncode == 0:
                return (Path(directory) / "uv.lock").read_text()
        raise self.UVError(f"Could not generate the lock file for `{self.name}`!")

    @classmethod
    def list(cls, root: Path = DIR) -> "list[UVN]":
        """List all virtual environments under a directory."""
        envs: "list[UVN]" = []
        for path in root.iterdir():
            if path.is_dir():
                try:
                    envs.append(cls(path))
                except EnvironmentError:
                    pass
        return envs

    class LinkMode(str, Enum):
        CLONE = "clone"
        COPY = "copy"
        HARDLINK = "hardlink"
        SYMLINK = "symlink"

    @classmethod
    def create(
        cls,
        name: str,
        *,
        root: Path = DIR,
        python: Optional[str] = None,
        link_mode: Optional[LinkMode] = None,
        quiet: bool = True,
    ) -> "UVN":
        """Create a virtual environment."""
        path = root / name
        try:
            cls(path)
        except cls.MissingError:
            opt = ["--no-project", "--no-config", "--python-preference", "only-managed"]
            if python:
                opt.extend(["--python", python])
            if link_mode:
                opt.extend(["--link-mode", link_mode])
            if quiet:
                opt.append("--quiet")
            run(["uv", "venv", *opt, path])
            return cls(path)
        except cls.CorruptedError as e:
            raise cls.ExistsError(f"Environment `{name}` exists but corrupted!") from e
        raise cls.ExistsError(f"Environment `{name}` exists!")

    @classmethod
    def remove(cls, name: str, *, root: Path = DIR, strict: bool = True) -> bool:
        """Remove a virtual environment."""
        path = root / name
        if strict:  # check if exists before removal
            return cls(path).remove(name, root=root, strict=False)
        if path.exists():
            shutil.rmtree(path)
            return True
        return False

    def export(
        self,
        target: Path,
        *,
        full: Optional[bool] = None,
        exact: Optional[bool] = None,
        quiet: bool = False,
    ) -> bool:
        """Export the virtual environment to a file (supports: txt, py, toml)."""
        kwargs = {}
        if full is not None:
            kwargs["full"] = full
        if exact is not None:
            kwargs["exact"] = exact
        if target.suffix == ".txt":
            text = self.get_requirements(**kwargs)
        elif target.suffix == ".toml":
            text = target.read_text() if target.exists() else ""
            text = self.get_pyproject(text, **kwargs)
        elif target.suffix == ".lock":
            text = self.get_lock(quiet=quiet)
        elif target.suffix == ".py":
            text = target.read_text() if target.exists() else ""
            text = self.get_script_metadata(text, **kwargs)
        else:
            raise self.FeatureError(f"Cannot handle this format yet `{target.name}`.")
        return target.write_text(text) == len(text)

    def fork(
        self,
        name: str,
        *,
        root: Path = DIR,
        link_mode: Optional[LinkMode] = None,
        quiet: bool = True,
    ) -> "UVN":
        """Fork a copy of the virtual environment."""
        env = self.create(
            name,
            root=root,
            python=self.full_version,
            link_mode=link_mode,
            quiet=quiet,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt") as file:
            file.write(self.get_requirements(full=True, exact=True))
            file.flush()
            opt = ["-r", file.name]
            if quiet:
                opt.append("--quiet")
            res = env.run(["uv", "pip", "install"] + opt)
        if res.returncode == 0:
            return env
        raise self.UVError(f"Installing packages with pip in `{env.name}`!")
