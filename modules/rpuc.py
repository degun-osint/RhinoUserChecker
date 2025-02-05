#!/usr/bin/env python3
# modules/rpuc.py
import aiohttp
import asyncio
import json
import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TimeRemainingColumn, TextColumn
from rich.live import Live
from jinja2 import Environment, BaseLoader
from urllib.parse import urlparse, quote
import logging
from typing import Dict, List, Optional
from dotenv import load_dotenv
from link_analyzer import analyze_links
from profile_extractor import extract_profile_info

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 50  # Process 50 requests simultaneously
MAX_CONNECTIONS = 200  # Maximum connections for aiohttp
REQUEST_TIMEOUT = 15
DEFAULT_JSON_URL = "https://raw.githubusercontent.com/degun-osint/WhatsMyName/main/wmn-data.json"
JSON_URL = os.getenv('WMN_JSON_URL', DEFAULT_JSON_URL)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
PROGRESS_DELAY = 0.01

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

PROXY_URL = os.getenv('PROXY_URL', 'http://127.0.0.1:8000/proxy')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

class SiteChecker:
    def __init__(self):
        """Initialize the site checker."""
        self.console = Console()
        self.sites = []
        self.results = []
        self.data_dir = DATA_DIR
        self.results_dir = RESULTS_DIR

    async def download_sites_data(self):
        """Download site data from configured URL."""
        local_file = os.path.join(self.data_dir, "wmn-data.json")

        try:
            async with aiohttp.ClientSession() as session:
                self.console.print(f"[cyan]Downloading data from {JSON_URL}...")
                async with session.get(JSON_URL) as response:
                    if response.status == 200:
                        data = await response.text()
                        json_data = json.loads(data)
                        self.sites = json_data.get('sites', [])
                        with open(local_file, 'w', encoding='utf-8') as f:
                            f.write(data)
                        self.console.print("[green]Data downloaded successfully")
                    else:
                        if os.path.exists(local_file):
                            self.console.print("[yellow]Using local data...")
                            with open(local_file, 'r', encoding='utf-8') as f:
                                json_data = json.load(f)
                                self.sites = json_data.get('sites', [])
                        else:
                            raise Exception("Unable to download data and no local data available")
        except Exception as e:
            if os.path.exists(local_file):
                self.console.print("[yellow]Using local data...")
                with open(local_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
                    self.sites = json_data.get('sites', [])
            else:
                raise

    async def verify_content(self, content: str, pattern: str, site_name: str) -> bool:
        """Check if pattern is present in content."""
        if not pattern:
            return True
        if not isinstance(content, str):
            return False

        normalized_content = ' '.join(content.split())
        normalized_pattern = ' '.join(pattern.split()).replace('\\"', '"')
        
        return normalized_pattern.lower() in normalized_content.lower()
    
    async def check_site(self, site: dict, username: str, session: aiohttp.ClientSession) -> Optional[dict]:
        """Check a specific site for a given username."""
        original_url = site['uri_check'].replace("{account}", username)
        display_url = site.get('uri_pretty', original_url).replace("{account}", username)

        if original_url.startswith('http://'):
            original_url = original_url.replace('http://', 'https://')

        try:
            # Use proxy
            proxy_url = f"{PROXY_URL}?url={quote(original_url)}"
            async with session.get(proxy_url, timeout=REQUEST_TIMEOUT) as response:
                if response.status != 200:
                    return None
                    
                json_response = await response.json()
                if not json_response or 'status' not in json_response:
                    return None

                content = json_response.get('contents', '')
                status_data = json_response['status']
                initial_status = status_data.get('initial_http_code', status_data.get('http_code'))

                # Verify status and patterns
                has_miss_string = await self.verify_content(content, site.get('m_string', ''), site['name'])
                has_expected_string = await self.verify_content(content, site.get('e_string', ''), site['name'])

                # Verification logic
                if initial_status == site['m_code'] and site['m_code'] != site['e_code']:
                    return None

                if initial_status == site['e_code'] and has_expected_string:
                    if not (site['m_code'] == site['e_code'] and has_miss_string):
                        # Analyze external links and extract profile info if profile is found
                        external_links = analyze_links(content, original_url)
                        profile_info = extract_profile_info(content, original_url)
                        
                        return {
                            'name': site['name'],
                            'category': site['cat'],
                            'url': display_url,
                            'status': 'found',
                            'http_code': initial_status,
                            'external_links': external_links,
                            'profile_info': profile_info
                        }

                return None

        except Exception as e:
            logger.error(f"Error checking {site['name']}: {str(e)}")
            return None

    async def process_batch(self, sites: List[dict], username: str) -> List[dict]:
        """Process a batch of sites in parallel."""
        connector = aiohttp.TCPConnector(limit=50, force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for site in sites:
                tasks.append(self.check_site(site, username, session))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            valid_results = []
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Error in batch: {str(r)}")
                    continue
                if r is not None:
                    valid_results.append(r)
            return valid_results

    async def check_username(self, username: str):
        """Check a username across all sites."""
        self.results = []
        console = Console()
        
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(complete_style="green", finished_style="green"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            main_task = progress.add_task(
                f"[cyan]🦏 Searching...", 
                total=len(self.sites)
            )
            
            found_count = 0
            tasks = []

            # Create all batches
            for i in range(0, len(self.sites), BATCH_SIZE):
                batch = self.sites[i:i + BATCH_SIZE]
                tasks.append(self.process_batch(batch, username))

            # Process batches in groups
            for i in range(0, len(tasks), 2):
                current_tasks = tasks[i:i+2]
                batch_results = await asyncio.gather(*current_tasks)
                
                sites_processed = min(BATCH_SIZE * 2, len(self.sites) - (i * BATCH_SIZE))
                
                for results in batch_results:
                    found_in_batch = len(results)
                    if found_in_batch > 0:
                        found_count += found_in_batch
                        for result in results:
                            console.print(f"[green]✓ Found on {result['name']}[/green]")
                
                progress.update(
                    main_task,
                    advance=sites_processed,
                    description=f"[cyan]🦏 Searching... ({found_count} found)"
                )
                
                await asyncio.sleep(PROGRESS_DELAY)
                
                for results in batch_results:
                    self.results.extend(results)

    def display_results_console(self):
        """Display results in console with styling."""
        if not self.results:
            self.console.print("\n[yellow]No profiles found[/yellow]")
            return

        table = Table(title=f"Search Results")
        
        table.add_column("Site", style="cyan")
        table.add_column("Category", style="green")
        table.add_column("Status", style="magenta")
        table.add_column("URL", style="blue")
        table.add_column("External Links", style="yellow")
        table.add_column("Profile Info", style="white")
        
        for result in self.results:
            external_links = result.get('external_links', [])
            links_str = ", ".join(external_links) if external_links else "-"
            
            # Format profile info
            profile_info = result.get('profile_info', {})
            profile_str = ""
            if profile_info:
                if profile_info.get('metadata'):
                    profile_str += "Metadata: " + ", ".join(f"{k}: {v}" for k, v in profile_info['metadata'].items())
                if profile_info.get('content'):
                    profile_str += "\nContent: " + ", ".join(profile_info['content'])
            
            table.add_row(
                result['name'],
                result['category'],
                result['status'],
                result['url'],
                links_str,
                profile_str or "-"
            )
        
        self.console.print(table)

    def export_html(self, output_file: str, username: str = ""):
        """Export results to HTML."""
        env = Environment(loader=BaseLoader())
        template_str = r'''
                    <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>RPUC Results</title>
                <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
                <style>
                    :root {
                        --primary: #1a1a1a;
                        --secondary: #2b2b2b;
                        --accent: #0f4c75;
                        --highlight: #00a8e8;
                        --success: #00ff9d;
                        --white: #ffffff;
                        --text-gray: #b3b3b3;
                    }

                    * {
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }

                    body {
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        line-height: 1.6;
                        background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                        color: var(--white);
                        min-height: 100vh;
                    }

                    .container {
                        max-width: 1200px;
                        margin: 0 auto;
                        padding: 2rem;
                    }

                    .header {
                        text-align: center;
                        padding: 2rem 0;
                        animation: fadeIn 1s ease-out;
                    }

                    .ascii-art {
                        font-family: monospace;
                        white-space: pre;
                        color: var(--highlight);
                        font-size: 0.7rem;
                        margin-bottom: 1rem;
                        text-align: left;
                        display: inline-block;
                    }

                    .header h1 {
                        font-size: 2.5rem;
                        margin-bottom: 1rem;
                        background: linear-gradient(45deg, var(--highlight), var(--success));
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
                    }

                    .timestamp {
                        background: var(--accent);
                        padding: 0.5rem 1rem;
                        border-radius: 20px;
                        display: inline-block;
                        font-size: 0.9rem;
                        margin-top: 1rem;
                        animation: slideIn 1s ease-out;
                    }

                    .results-container {
                        background: rgba(15, 15, 15, 0.7);
                        backdrop-filter: blur(10px);
                        border-radius: 15px;
                        padding: 2rem;
                        margin-top: 2rem;
                        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                        animation: fadeIn 1.5s ease-out;
                        border: 1px solid rgba(255, 255, 255, 0.1);
                    }

                    .results-table {
                        width: 100%;
                        border-collapse: separate;
                        border-spacing: 0 8px;
                        margin-top: 1rem;
                    }

                    .results-table th {
                        background: var(--accent);
                        color: var(--white);
                        padding: 1rem;
                        text-align: left;
                        font-weight: 600;
                        text-transform: uppercase;
                        letter-spacing: 1px;
                        font-size: 0.9rem;
                    }

                    .results-table th:first-child {
                        border-radius: 10px 0 0 10px;
                    }

                    .results-table th:last-child {
                        border-radius: 0 10px 10px 0;
                    }

                    .results-table tr {
                        transition: transform 0.2s ease, background-color 0.3s ease;
                    }

                    .results-table tr:hover {
                        transform: translateY(-2px);
                        background: rgba(0, 168, 232, 0.1);
                    }

                    .results-table td {
                        background: rgba(43, 43, 43, 0.5);
                        padding: 1rem;
                        transition: all 0.3s ease;
                    }

                    .results-table tr td:first-child {
                        border-radius: 10px 0 0 10px;
                    }

                    .results-table tr td:last-child {
                        border-radius: 0 10px 10px 0;
                    }

                    .external-links a {
                        color: var(--highlight);
                        text-decoration: none;
                        margin-right: 1rem;
                        transition: color 0.3s ease;
                        display: inline-block;
                        padding: 0.2rem 0;
                    }

                    .external-links a:hover {
                        color: var(--success);
                    }

                    .profile-info {
                        font-size: 0.9rem;
                    }

                    .metadata {
                        background: rgba(15, 76, 117, 0.2);
                        padding: 1rem;
                        border-radius: 8px;
                        margin-bottom: 1rem;
                        border: 1px solid rgba(0, 168, 232, 0.2);
                    }

                    .content {
                        color: var(--text-gray);
                    }

                    .no-results {
                        text-align: center;
                        padding: 3rem;
                        font-size: 1.2rem;
                        color: var(--highlight);
                    }

                    .icon {
                        margin-right: 0.5rem;
                        color: var(--highlight);
                    }

                    @keyframes fadeIn {
                        from { opacity: 0; }
                        to { opacity: 1; }
                    }

                    @keyframes slideIn {
                        from {
                            transform: translateY(-20px);
                            opacity: 0;
                        }
                        to {
                            transform: translateY(0);
                            opacity: 1;
                        }
                    }

                    @media (max-width: 768px) {
                        .container {
                            padding: 1rem;
                        }

                        .results-table {
                            display: block;
                            overflow-x: auto;
                        }

                        .header h1 {
                            font-size: 2rem;
                        }

                        .ascii-art {
                            font-size: 0.5rem;
                        }
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <header class="header">
                        <pre class="ascii-art">
            .----------------------------------------------.
           ( RHINO USER CHECKER v0.8 - OSCAR ZULU FOREVER ! )
          //\'---------------------------------------------'\
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
                        </pre>
                        <h1>Rhino User Checker Results</h1>
                        <h2 style="color: var(--highlight); margin-bottom: 1rem;">Results for: {{ username }}</h2>
                        <div class="timestamp"><i class="far fa-clock icon"></i>Generated on {{ timestamp }}</div>
                    </header>
                        {% if results %}
                        <table class="results-table">
                            <thead>
                                <tr>
                                    <th><i class="fas fa-globe icon"></i>Site</th>
                                    <th><i class="fas fa-tag icon"></i>Category</th>
                                    <th><i class="fas fa-link icon"></i>URL</th>
                                    <th><i class="fas fa-external-link-alt icon"></i>External Links</th>
                                    <th><i class="fas fa-user-circle icon"></i>Profile Information</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for result in results %}
                                <tr>
                                    <td>{{ result.name }}</td>
                                    <td>{{ result.category }}</td>
                                    <td class="external-links">
                                        <a href="{{ result.url }}" target="_blank" ><i class="fas fa-external-link-alt icon"></i>{{ result.url }}</a>
                                        </td>
                                    <td class="external-links">
                                        {% if result.external_links %}
                                            {% for link in result.external_links %}
                                                <a href="{{ link }}" target="_blank"><i class="fas fa-external-link-alt icon"></i>{{ link }}</a>
                                            {% endfor %}
                                        {% else %}
                                            -
                                        {% endif %}
                                    </td>
                                    <td class="profile-info">
                                        {% if result.profile_info %}
                                            {% if result.profile_info.metadata %}
                                                <div class="metadata">
                                                    <strong><i class="fas fa-database icon"></i>Metadata:</strong><br>
                                                    {% for key, value in result.profile_info.metadata.items() %}
                                                        {{ key }}: {{ value }}<br>
                                                    {% endfor %}
                                                </div>
                                            {% endif %}
                                            {% if result.profile_info.content %}
                                                <div class="content">
                                                    <strong><i class="fas fa-file-alt icon"></i>Content:</strong><br>
                                                    {% for item in result.profile_info.content %}
                                                        {{ item }}<br>
                                                    {% endfor %}
                                                </div>
                                            {% endif %}
                                        {% else %}
                                            -
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                        {% else %}
                        <div class="no-results">
                            <i class="fas fa-search icon"></i>No profiles found
                        </div>
                        {% endif %}
                </div>
            </body>
            </html>
                    '''
        
        template = env.from_string(template_str)
        html_content = template.render(
            results=self.results,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            username=username
        )
        
        output_path = os.path.join(self.results_dir, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return output_path
    
    def export_results_csv(self, output_file: str):
        """Export results to CSV format."""
        import csv
        output_path = os.path.join(self.results_dir, output_file)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write headers
            headers = ['Site', 'Category', 'Status', 'URL', 'External Links', 'Profile Info']
            writer.writerow(headers)
            
            # Write data
            for result in self.results:
                external_links = '; '.join(result.get('external_links', []))
                
                # Format profile info
                profile_info = result.get('profile_info', {})
                profile_str = ''
                if profile_info:
                    if profile_info.get('metadata'):
                        profile_str += 'Metadata: ' + ', '.join(f"{k}: {v}" for k, v in profile_info['metadata'].items())
                    if profile_info.get('content'):
                        profile_str += ' | Content: ' + ', '.join(profile_info['content'])
                
                row = [
                    result['name'],
                    result['category'],
                    result['status'],
                    result['url'],
                    external_links,
                    profile_str
                ]
                writer.writerow(row)
                
        return output_path

async def main():
    try:
        checker = SiteChecker()
        await checker.download_sites_data()
        
        username = input("\nEnter username to search: ")
        
        while True:
            if not username.strip():
                print("Username cannot be empty")
                username = input("\nEnter username to search: ")
                continue
                
            print(f"\nSearching profiles for {username}...")
            await checker.check_username(username)
            
            checker.display_results_console()
            
            # Ask for export format
            while True:
                export_choice = input("\nDo you want to export results? (CSV / HTML / BOTH / NO): ").upper()
                if export_choice in ['CSV', 'HTML', 'BOTH', 'NO']:
                    break
                print("Invalid choice. Please enter CSV, HTML, BOTH, or NO.")
            
            if export_choice != 'NO':
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                if export_choice in ['HTML', 'BOTH']:
                    output_file = f"results_{username}_{timestamp}.html"
                    output_path_html = checker.export_html(output_file, username=username)
                    print(f"\nHTML results exported to {output_path_html}")
                
                if export_choice in ['CSV', 'BOTH']:
                    output_file = f"results_{username}_{timestamp}.csv"
                    output_path_csv = checker.export_results_csv(output_file)
                    print(f"CSV results exported to {output_path_csv}")
            
            # Ask to search another user
            username = input("\nSearch another user? (enter alias or ctrl-c to quit): ")
            if not username.strip():
                break
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user...")
    except asyncio.CancelledError:
        print("\nOperation cancelled...")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")

def run():
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    run()