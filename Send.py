import os
import socket
import time
from plyer import notification
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

BUFFER_SIZE = 1024 * 1024  # 1MB chunks
BANNER = """
 █▀▀ █▀▀ █▄ █ █▀▄ █▀▀ █▀█ 
 ▄██ ██▄ █ ▀█ █▄▀ ██▄ █▀▄ 
        >> FILE SENDER <<
"""

console = Console()

def main():
    console.clear()
    console.print(Panel(BANNER, style="bold cyan", expand=False))
    
    host = Prompt.ask("[bold white]Enter the Receiver's IP Address[/bold white]", default="127.0.0.1")
    port = 5001
    
    while True:
        filepath = Prompt.ask("[bold white]Drag & drop or enter file path[/bold white]").strip('\'"')
        if os.path.exists(filepath):
            break
        console.print("[bold red][!] File not found. Please try again.[/bold red]")

    filesize = os.path.getsize(filepath)
    filename = os.path.basename(filepath)

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        console.print(f"\n[bold blue][*][/bold blue] Connecting to [yellow]{host}:{port}[/yellow]...")
        client.connect((host, port))
        console.print("[bold green][✓] Connected. Starting stream...[/bold green]\n")

        # FIX: Force exact 1024 byte layout padded with spaces
        metadata = f"{filename}|{filesize}"
        client.sendall(metadata.encode('utf-8').ljust(1024))
        
        # Give network stack a momentary pause to flush metadata out of buffer
        time.sleep(0.1)

        # Stream file data
        with open(filepath, "rb") as f:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                task = progress.add_task(f"[cyan]Uploading {filename}", total=filesize)
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    client.sendall(chunk)
                    progress.update(task, advance=len(chunk))

        console.print("\n[bold green][✓] File sent successfully![/bold green]")
        
        notification.notify(
            title="File Transfer Complete",
            message=f"Successfully sent: {filename}",
            app_name="Traxfer",
            timeout=5
        )

    except ConnectionRefusedError:
        console.print("\n[bold red][!] Connection refused. Make sure receive.py is running on the target machine.[/bold red]")
    except Exception as e:
        console.print(f"\n[bold red][!] Error during transfer:[/bold red] {e}")
    finally:
        client.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Program closed.[/yellow]")
