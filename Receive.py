import os
import socket
import sys
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, TextColumn,
    BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
)
from rich.table import Table
from rich.text import Text
from rich import box
from rich.align import Align
from rich.rule import Rule
from rich.prompt import Prompt

BUFFER_SIZE = 1024 * 1024  # 1 MB chunks
META_SIZE   = 1024          # must match Send.py
PORT        = 5001

console = Console()

BANNER = """\
╔══════════════════════════════════════╗
║  ██████╗ ███████╗ ██████╗██╗   ██╗  ║
║  ██╔══██╗██╔════╝██╔════╝██║   ██║  ║
║  ██████╔╝█████╗  ██║     ██║   ██║  ║
║  ██╔══██╗██╔══╝  ██║     ╚██╗ ██╔╝  ║
║  ██║  ██║███████╗╚██████╗ ╚████╔╝   ║
║  ╚═╝  ╚═╝╚══════╝ ╚═════╝  ╚═══╝   ║
║        FILE  RECEIVER  v2.0          ║
╚══════════════════════════════════════╝"""


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


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def resolve_output_path(directory: str, filename: str) -> str:
    """
    Return a collision-free output path inside `directory`.
    If 'received_filename.ext' already exists, append _1, _2, … until free.
    """
    os.makedirs(directory, exist_ok=True)
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(directory, f"received_{base}{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(directory, f"received_{base}_{counter}{ext}")
        counter += 1
    return candidate


def print_header() -> None:
    console.clear()
    console.print()
    console.print(Align.center(
        Panel(Text(BANNER, style="bold green", justify="center"),
              border_style="bright_green", padding=(0, 2), expand=False)
    ))
    console.print()


def show_network_info(ip: str) -> None:
    table = Table(box=box.ROUNDED, border_style="green", show_header=False,
                  padding=(0, 2))
    table.add_column(style="bold bright_white", min_width=16)
    table.add_column(style="yellow")
    table.add_row("Your IP (give to sender)", ip)
    table.add_row("Listening on port",        str(PORT))
    console.print(Align.center(table))
    console.print()


def show_incoming_info(sender_ip: str, filename: str, filesize: int,
                       output_path: str) -> None:
    table = Table(box=box.ROUNDED, border_style="cyan", show_header=False,
                  padding=(0, 2))
    table.add_column(style="bold bright_white", min_width=14)
    table.add_column(style="yellow")
    table.add_row("From",       sender_ip)
    table.add_row("File name",  filename)
    table.add_row("File size",  format_size(filesize))
    table.add_row("Saving as",  output_path)
    console.print()
    console.print(Align.center(table))
    console.print()


def receive_file(conn: socket.socket, addr: tuple, output_dir: str) -> None:
    sender_ip = addr[0]

    # ── Read exactly META_SIZE bytes for the metadata frame ─────────────────
    metadata_bytes = b""
    while len(metadata_bytes) < META_SIZE:
        chunk = conn.recv(META_SIZE - len(metadata_bytes))
        if not chunk:
            break
        metadata_bytes += chunk

    if len(metadata_bytes) < META_SIZE:
        console.print(
            "[bold red]  ✗  Incomplete metadata frame received.[/bold red]"
        )
        return

    # Strip null-byte padding (Send.py pads with \x00)
    metadata = metadata_bytes.rstrip(b"\x00").decode("utf-8", errors="replace")

    if not metadata or "|" not in metadata:
        console.print(
            "[bold red]  ✗  Invalid metadata — could not parse filename/size.[/bold red]"
        )
        return

    # rsplit so filenames that contain '|' still work
    filename, _, size_str = metadata.rpartition("|")
    filename = filename.strip()

    if not filename:
        console.print(
            "[bold red]  ✗  Empty filename in metadata.[/bold red]"
        )
        return

    try:
        filesize = int(size_str.strip())
    except ValueError:
        console.print(
            f"[bold red]  ✗  Bad file size in metadata: {size_str!r}[/bold red]"
        )
        return

    if filesize <= 0:
        console.print(
            "[bold yellow]  ⚠  Sender reported 0-byte file — nothing to save.[/bold yellow]"
        )
        return

    output_path = resolve_output_path(output_dir, filename)
    show_incoming_info(sender_ip, filename, filesize, output_path)

    # ── Stream file data ─────────────────────────────────────────────────────
    try:
        with open(output_path, "wb") as f:
            with Progress(
                SpinnerColumn(style="green"),
                TextColumn("[progress.description]{task.description}",
                           style="white"),
                BarColumn(bar_width=36, style="green",
                          complete_style="bold bright_green"),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task(
                    f"[green]  Receiving[/green] [white]{filename}[/white]",
                    total=filesize
                )
                bytes_received = 0
                while bytes_received < filesize:
                    to_read = min(BUFFER_SIZE, filesize - bytes_received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_received += len(chunk)
                    progress.update(task, advance=len(chunk))

        if bytes_received < filesize:
            console.print(
                f"\n  [bold yellow]⚠  Incomplete transfer:[/bold yellow] "
                f"received {format_size(bytes_received)} of {format_size(filesize)}. "
                "The sender may have disconnected early."
            )
            return

    except OSError as exc:
        console.print(
            f"\n  [bold red]✗  Could not write file:[/bold red] {exc}"
        )
        return

    console.print()
    console.print(Rule(style="bright_green"))
    console.print(
        f"  [bold green]✓  Transfer complete![/bold green]  "
        f"[dim]{format_size(bytes_received)} received[/dim]"
    )
    console.print(
        f"  [dim]Saved →[/dim] [yellow]{output_path}[/yellow]"
    )
    console.print(Rule(style="bright_green"))
    console.print()

    notify("Transfer Complete", f"Received: {os.path.basename(output_path)}")


def main() -> None:
    print_header()

    local_ip = get_local_ip()
    show_network_info(local_ip)

    # Let the user choose the save directory (default: current dir)
    default_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Traxfer")
    output_dir = Prompt.ask(
        "[bold white]  💾  Save files to[/bold white]",
        default=default_dir
    ).strip().strip('\'"') or default_dir

    console.print()
    console.print(Rule("[dim]Waiting for connection[/dim]", style="dim green"))
    console.print()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    conn = None  # track so we can close it in finally

    try:
        server.bind(("0.0.0.0", PORT))
        server.listen(1)
        console.print(
            f"  [bold blue]⟶[/bold blue]  Listening on "
            f"[yellow]0.0.0.0:{PORT}[/yellow] — waiting for sender …"
        )

        conn, addr = server.accept()
        console.print(
            f"  [bold green]✓[/bold green]  Sender connected from "
            f"[yellow]{addr[0]}[/yellow]\n"
        )

        receive_file(conn, addr, output_dir)

    except KeyboardInterrupt:
        console.print(
            "\n\n  [bold yellow]✗  Interrupted by user.[/bold yellow]\n"
        )
    except OSError as exc:
        # e.g. address already in use
        console.print(f"\n  [bold red]✗  Socket error:[/bold red] {exc}")
    except Exception as exc:
        console.print(f"\n  [bold red]✗  Unexpected error:[/bold red] {exc}")
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        server.close()


if __name__ == "__main__":
    main()
