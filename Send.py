import os
import socket
import time
import sys
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
)
from rich.table import Table
from rich.text import Text
from rich import box
from rich.align import Align
from rich.rule import Rule

BUFFER_SIZE = 1024 * 1024  # 1 MB chunks
META_SIZE   = 1024          # fixed metadata frame size (bytes)
PORT        = 5001
CONNECT_TIMEOUT = 10        # seconds

console = Console()

BANNER = """\
╔════════════════════════════════╗
║  ████████╗██████╗  █████╗ ██╗ ║
║     ██╔══╝██╔══██╗██╔══██╗██║ ║
║     ██║   ██████╔╝███████║██║ ║
║     ██║   ██╔══██╗██╔══██║╚═╝ ║
║     ██║   ██║  ██║██║  ██║██╗ ║
║     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝ ║
║        FILE  SENDER  v2.0      ║
╚════════════════════════════════╝"""


def notify(title: str, message: str) -> None:
    """Desktop notification — silently skipped if unavailable."""
    try:
        from plyer import notification
        notification.notify(title=title, message=message,
                            app_name="Traxfer", timeout=5)
    except Exception:
        pass


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def print_header() -> None:
    console.clear()
    console.print()
    console.print(Align.center(
        Panel(Text(BANNER, style="bold cyan", justify="center"),
              border_style="bright_cyan", padding=(0, 2), expand=False)
    ))
    console.print()


def get_file_path() -> str:
    while True:
        path = Prompt.ask(
            "[bold white]  📁  File path[/bold white]"
        ).strip().strip('\'"')
        if not path:
            console.print("[bold red]  ✗  Path cannot be empty.[/bold red]")
            continue
        if not os.path.exists(path):
            console.print("[bold red]  ✗  File not found. Try again.[/bold red]")
            continue
        if not os.path.isfile(path):
            console.print("[bold red]  ✗  Path is a directory, not a file.[/bold red]")
            continue
        size = os.path.getsize(path)
        if size == 0:
            console.print("[bold yellow]  ⚠  File is empty (0 bytes). Aborting.[/bold yellow]")
            continue
        return path


def show_file_info(filename: str, filesize: int, host: str) -> None:
    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False,
                  padding=(0, 2))
    table.add_column(style="bold bright_white", min_width=12)
    table.add_column(style="yellow")
    table.add_row("File",        filename)
    table.add_row("Size",        format_size(filesize))
    table.add_row("Destination", f"{host}:{PORT}")
    console.print()
    console.print(Align.center(table))
    console.print()


def send_file(filepath: str, host: str) -> None:
    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    show_file_info(filename, filesize, host)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(CONNECT_TIMEOUT)

    try:
        console.print(
            f"  [bold blue]⟶[/bold blue]  Connecting to "
            f"[yellow]{host}:{PORT}[/yellow] …"
        )
        client.connect((host, PORT))
        client.settimeout(None)          # remove timeout once connected
        console.print(
            "  [bold green]✓[/bold green]  Connected — starting transfer\n"
        )

        # ── Send metadata (exactly META_SIZE bytes, zero-padded) ──────────────
        # Use b'\x00' padding so receiver can strip reliably regardless of
        # filename content.
        metadata_str = f"{filename}|{filesize}"
        metadata_bytes = metadata_str.encode("utf-8")
        if len(metadata_bytes) > META_SIZE - 1:
            console.print(
                "[bold red]  ✗  Filename too long to fit in metadata frame.[/bold red]"
            )
            return
        # Pad with null bytes to exactly META_SIZE
        padded = metadata_bytes.ljust(META_SIZE, b"\x00")
        client.sendall(padded)

        # Brief pause so the TCP stack flushes metadata before the raw stream
        time.sleep(0.05)

        # ── Stream file ───────────────────────────────────────────────────────
        with open(filepath, "rb") as f:
            with Progress(
                SpinnerColumn(style="cyan"),
                TextColumn("[progress.description]{task.description}",
                           style="white"),
                BarColumn(bar_width=36, style="cyan",
                          complete_style="bold green"),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]  Uploading[/cyan] [white]{filename}[/white]",
                    total=filesize
                )
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    client.sendall(chunk)
                    progress.update(task, advance=len(chunk))

        # Graceful shutdown — signal EOF to receiver
        client.shutdown(socket.SHUT_WR)

        console.print()
        console.print(Rule(style="green"))
        console.print(
            f"  [bold green]✓  Transfer complete![/bold green]  "
            f"[dim]({format_size(filesize)} sent)[/dim]"
        )
        console.print(Rule(style="green"))
        console.print()

        notify("Transfer Complete", f"Sent: {filename}")

    except socket.timeout:
        console.print(
            f"\n  [bold red]✗  Connection timed out[/bold red] after "
            f"{CONNECT_TIMEOUT}s. "
            "Is Receive.py running on the target machine?"
        )
    except ConnectionRefusedError:
        console.print(
            "\n  [bold red]✗  Connection refused.[/bold red] "
            "Make sure Receive.py is running on the target machine."
        )
    except BrokenPipeError:
        console.print(
            "\n  [bold red]✗  Connection lost mid-transfer.[/bold red] "
            "The receiver may have disconnected."
        )
    except Exception as exc:
        console.print(f"\n  [bold red]✗  Unexpected error:[/bold red] {exc}")
    finally:
        client.close()


def main() -> None:
    print_header()

    host = Prompt.ask(
        "[bold white]  🌐  Receiver IP address[/bold white]",
        default="127.0.0.1"
    ).strip()

    console.print()
    console.print(Rule("[dim]File Selection[/dim]", style="dim cyan"))
    console.print()

    filepath = get_file_path()
    send_file(filepath, host)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n  [yellow]Cancelled.[/yellow]\n")
        sys.exit(0)
