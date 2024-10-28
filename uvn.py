import typer

__version__ = "0.0.0"

app = typer.Typer()

@app.command()
def main() -> None:
    print("Hello from uvn!")
