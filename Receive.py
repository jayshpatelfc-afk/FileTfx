import os
import socket
from plyer import notification
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

BUFFER_SIZE = 1024 * 1024  # 1MB chunks
BANNER = """
 █▀█ █▀▀ █▀▀ █▀▀ █ █ █ █ █▀▀ 
 █▀▄ █▀▀ █▄▄ █▀▀ ▀▄▀ █ █ █▀▀ 
       >> FILE RECEIVER <<
"""

console = Console()

def get_local_ips():
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        ips.append("127.0.0.1")
    return ips

def main():
    console.clear()
    console.print(Panel(BANNER, style="bold green", expand=False))
    
    local_ips = get_local_ips()
    port = 5001
    
    console.print(Panel(
        f"Give this IP to the sender: [bold yellow]{', '.join(local_ips)}[/bold yellow]\n"
        f"Listening on Port: [yellow]{port}[/yellow]",
        title="[bold white]Receiver Network Info[/bold white]", border_style="green"
    ))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind(('0.0.0.0', port))
        server.listen(1)
        console.print("[bold blue][*][/bold blue] Waiting for the sender to connect...")
        
        conn, addr = server.accept()
        console.print(f"[bold green][✓][/bold green] Connected to sender at [yellow]{addr[0]}[/yellow]\n")

        # Read metadata
        metadata = conn.recv(1024).decode('utf-8').strip()
        if not metadata or "|" not in metadata:
            console.print("[bold red][!] Invalid metadata received.[/bold red]")
            return
        
        filename, filesize = metadata.split("|")
        filesize = int(filesize)
        output_filename = f"received_{os.path.basename(filename)}"
        
        # Stream file
        with open(output_filename, "wb") as f:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"[green]Downloading {output_filename}", total=filesize)
                bytes_received = 0
                while bytes_received < filesize:
                    to_read = min(BUFFER_SIZE, filesize - bytes_received)
                    chunk = conn.recv(to_read)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_received += len(chunk)
                    progress.update(task, advance=len(chunk))

        console.print(f"\n[bold green][✓] Success![/bold green] Saved as: [yellow]{output_filename}[/yellow]")
        
        # OS Desktop Notification
        notification.notify(
            title="File Transfer Complete",
            message=f"Successfully received: {output_filename}",
            app_name="Traxfer",
            timeout=5
        )

    except KeyboardInterrupt:
        console.print("\n[bold yellow][!] Transfer aborted by user.[/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red][!] Error:[/bold red] {e}")
    finally:
        server.close()

if __name__ == "__main__":
    main()