#!/usr/bin/env python3
# run.py

import subprocess
import sys
import time
import signal
import os
import psutil
from rich.console import Console

# Path configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODULES_DIR = os.path.join(BASE_DIR, "modules")
PROXY_PATH = os.path.join(MODULES_DIR, "proxy.py")
RPUC_PATH = os.path.join(MODULES_DIR, "rpuc.py")
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# Create necessary directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

console = Console()

def kill_process_tree(pid):
    """Kill a process and all its children."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass

def cleanup(proxy_process, main_process):
    """Clean up processes on shutdown."""
    if main_process:
        kill_process_tree(main_process.pid)
    if proxy_process:
        kill_process_tree(proxy_process.pid)

def run_proxy():
    """Start the proxy server without changing the global directory."""
    try:
        return subprocess.Popen([sys.executable, PROXY_PATH],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                cwd=MODULES_DIR)
    except Exception as e:
        console.print(f"[red]Error starting proxy: {e}[/red]")
        sys.exit(1)

def run_main():
    """Start the main script without changing the global directory."""
    try:
        return subprocess.Popen([sys.executable, RPUC_PATH],
                                cwd=MODULES_DIR)
    except Exception as e:
        console.print(f"[red]Error starting main script: {e}[/red]")
        return None

def print_banner():
    banner = r"""
            .-----------------------------------------.
           ( RHINO USER CHECKER - OSCAR ZULU FOREVER ! )
          //\'----------------------------------------'\
         /      , _.-~~-.__            __.,----.
      (';    __( )         ~~~'--..--~~         '.
(    . ""..-'  ')|                     .       \  '.
 \\. |\'.'                    ;       .  ;       ;   ;
  \ \"   /9)                 '       .  ;           ;
   ; )           )    (        '       .  ;     '    .
    )    _  __.-'-._   ;       '       . ,     /\    ;
    '-"'--'      ; "-. '.    '            _.-(  ".  (
                  ;    \,)    )--,..----';'    >  ;   .
                   \   ( |   /           (    /   .   ;
     ,   ,          )  | ; .(      .    , )  /     \  ;
,;'PjP;.';-.;._,;/;,;)/;.;.);.;,,;,;,,;/;;,),;.,/,;.).,;

    """
    console.print("[yellow]" + banner + "[/yellow]")

def print_title():
    title = "Username, profile info and link scrapper \n"
    credits = "Based on Whatsmyname JSON (https://github.com/WebBreacher/WhatsMyName)\n"
    console.print("[bold cyan]" + title + "[/bold cyan]")
    console.print("[italic dim cyan]" + credits + "[/italic dim cyan]")

def main():
    # Display banner
    print_banner()
    print_title()

    # Check file existence
    if not os.path.exists(PROXY_PATH):
        console.print(f"[red]Error: {PROXY_PATH} does not exist[/red]")
        sys.exit(1)
    if not os.path.exists(RPUC_PATH):
        console.print(f"[red]Error: {RPUC_PATH} does not exist[/red]")
        sys.exit(1)

    proxy_process = None
    main_process = None

    def signal_handler(signum, frame):
        console.print("\n[yellow]Stopping processes...[/yellow]")
        cleanup(proxy_process, main_process)
        sys.exit(0)

    # Signal handling
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start proxy
        console.print("[cyan]Starting proxy...[/cyan]")
        proxy_process = run_proxy()
        
        # Wait for proxy to be ready
        time.sleep(2)
        
        # Start main script
        console.print("[cyan]Starting main script...[/cyan]")
        main_process = run_main()

        while True:
            if main_process.poll() is not None:
                break
            time.sleep(0.1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user...[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
    finally:
        cleanup(proxy_process, main_process)
        console.print("[green]Processes stopped[/green]")

if __name__ == "__main__":
    main()