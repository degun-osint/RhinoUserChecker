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
from date_extractor import extract_profile_date, normalize_date
import re

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
            
    def is_date_status(self, status):
        """Détermine si le statut contient une date."""
        if not isinstance(status, str):
            return False
            
        status_lower = status.lower()
        
        # Vérifie si "join" ou un nom de mois est présent
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        if 'join' in status_lower or any(month in status_lower for month in months):
            return True
            
        # Vérifie s'il y a au moins un chiffre
        if any(c.isdigit() for c in status_lower):
            return True
            
        return False

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

                if initial_status == site['e_code']:
                    # Case où on a trouvé le profil avec certitude
                    if has_expected_string:
                        if not (site['m_code'] == site['e_code'] and has_miss_string):
                            external_links = analyze_links(content, original_url)
                            profile_info = extract_profile_info(content, original_url)
                            
                            # Extraire la date de création du profil
                            profile_date = None
                            if profile_info and 'metadata' in profile_info:
                                profile_date = extract_profile_date(content, profile_info.get('metadata', {}), site_name=site['name'])
                            
                            # Déterminer le statut (date de création ou "found")
                            status = 'found'
                            if profile_date:
                                status = normalize_date(profile_date)
                                
                            # Vérifier si le contenu provient d'une balise link rel (à ignorer)
                            if status != 'found' and "<link rel=" in content and re.search(r'<link\s+rel=["\'].*?\b' + re.escape(status) + r'\b.*?["\']', content, re.IGNORECASE):
                                status = 'found'
                            
                            return {
                                'name': site['name'],
                                'category': site['cat'],
                                'url': display_url,
                                'status': status,  # Utiliser la date si disponible
                                'http_code': initial_status,
                                'external_links': external_links,
                                'profile_info': profile_info
                            }
                    # Nouveau cas "unsure" : on a le bon code mais pas la string attendue
                    elif site['m_code'] == 404:  # On vérifie que c'est bien un cas où on attendait un 404 pour les non-trouvés
                        external_links = analyze_links(content, original_url)
                        profile_info = extract_profile_info(content, original_url)
                        
                        # Ne pas extraire de date pour les profils "unsure"
                        return {
                            'name': site['name'],
                            'category': site['cat'],
                            'url': display_url,
                            'status': 'unsure',  # Toujours garder "unsure"
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
            status_style = "green" if result['status'] == 'found' else "yellow" if result['status'] == 'unsure' else "white"
            
            external_links = result.get('external_links', [])
            links_str = ", ".join(external_links) if external_links else "-"
            
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
                f"[{status_style}]{result['status']}[/{status_style}]",
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
                                --warning: #FFA500;
                                --date: #00BFFF;
                                --white: #ffffff;
                                --text-gray: #b3b3b3;
                                --card-bg: rgba(43, 43, 43, 0.5);
                                --content-bg: rgba(15, 15, 15, 0.7);
                            }

                            * {
                                margin: 0;
                                padding: 0;
                                box-sizing: border-box;
                                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                            }

                            body {
                                line-height: 1.6;
                                background: linear-gradient(135deg, var(--primary) 0%, var(--secondary) 100%);
                                color: var(--white);
                                min-height: 100vh;
                                font-size: 16px;
                            }

                            .container {
                                max-width: 1400px;
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

                            .stats-container {
                                display: flex;
                                flex-wrap: wrap;
                                justify-content: center;
                                gap: 1rem;
                                margin: 2rem 0;
                            }

                            .stat-card {
                                background: var(--accent);
                                padding: 1rem;
                                border-radius: 10px;
                                min-width: 150px;
                                text-align: center;
                                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                            }

                            .stat-value {
                                font-size: 1.8rem;
                                font-weight: bold;
                                margin-bottom: 0.5rem;
                            }

                            .stat-label {
                                font-size: 0.9rem;
                                opacity: 0.9;
                            }

                            .results-grid {
                                display: grid;
                                grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
                                gap: 1.5rem;
                                margin-top: 2rem;
                            }

                            .profile-card {
                                background: var(--card-bg);
                                border-radius: 10px;
                                overflow: hidden;
                                box-shadow: 0 8px 24px rgba(0,0,0,0.2);
                                transition: transform 0.3s ease, box-shadow 0.3s ease;
                                display: flex;
                                flex-direction: column;
                            }

                            .profile-card:hover {
                                transform: translateY(-5px);
                                box-shadow: 0 12px 32px rgba(0,0,0,0.3);
                            }

                            .card-header {
                                background: var(--accent);
                                padding: 1rem;
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
                            }

                            .site-info {
                                display: flex;
                                align-items: center;
                                gap: 0.5rem;
                            }

                            .site-name {
                                font-weight: bold;
                                font-size: 1.2rem;
                            }

                            .site-category {
                                background: rgba(0,0,0,0.2);
                                padding: 0.2rem 0.5rem;
                                border-radius: 12px;
                                font-size: 0.8rem;
                            }

                            .status-badge {
                                padding: 0.3rem 0.8rem;
                                border-radius: 20px;
                                font-size: 0.9rem;
                                font-weight: 500;
                                display: flex;
                                align-items: center;
                                gap: 0.3rem;
                            }

                            .status-found {
                                background: var(--success);
                                color: #000;
                            }

                            .status-unsure {
                                background: var(--warning);
                                color: #000;
                            }

                            .status-date {
                                background: var(--date);
                                color: #000;
                            }

                            .card-body {
                                padding: 1rem;
                                flex-grow: 1;
                                display: flex;
                                flex-direction: column;
                                gap: 1rem;
                            }

                            .url-container {
                                word-break: break-all;
                            }

                            .url-link {
                                color: var(--highlight);
                                text-decoration: none;
                                transition: color 0.2s ease;
                                display: flex;
                                align-items: center;
                                gap: 0.5rem;
                            }

                            .url-link:hover {
                                color: var(--success);
                            }

                            .external-links-container {
                                margin-top: 0.5rem;
                            }

                            .external-links-title {
                                font-size: 0.9rem;
                                margin-bottom: 0.5rem;
                                color: var(--text-gray);
                            }

                            .external-links {
                                display: flex;
                                flex-wrap: wrap;
                                gap: 0.5rem;
                            }

                            .external-link {
                                color: var(--highlight);
                                text-decoration: none;
                                background: rgba(0, 168, 232, 0.1);
                                padding: 0.3rem 0.6rem;
                                border-radius: 5px;
                                font-size: 0.85rem;
                                transition: all 0.2s ease;
                                max-width: 100%;
                                overflow: hidden;
                                text-overflow: ellipsis;
                                white-space: nowrap;
                            }

                            .external-link:hover {
                                background: rgba(0, 168, 232, 0.2);
                                color: var(--success);
                            }

                            .profile-info {
                                margin-top: 0.5rem;
                            }

                            .metadata, .content {
                                background: rgba(15, 76, 117, 0.2);
                                padding: 0.8rem;
                                border-radius: 8px;
                                margin-bottom: 0.8rem;
                                border: 1px solid rgba(0, 168, 232, 0.2);
                                font-size: 0.9rem;
                            }

                            .content {
                                color: var(--text-gray);
                            }

                            .info-title {
                                display: flex;
                                align-items: center;
                                gap: 0.5rem;
                                margin-bottom: 0.5rem;
                                font-weight: 600;
                            }

                            .metadata-items, .content-items {
                                display: flex;
                                flex-direction: column;
                                gap: 0.3rem;
                            }

                            .metadata-item, .content-item {
                                line-height: 1.4;
                            }

                            .icon {
                                color: var(--highlight);
                            }

                            .no-results {
                                text-align: center;
                                padding: 3rem;
                                font-size: 1.2rem;
                                color: var(--highlight);
                                background: var(--content-bg);
                                backdrop-filter: blur(10px);
                                border-radius: 15px;
                                margin-top: 2rem;
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

                            /* Styles pour la version mobile et tablette */
                            @media (max-width: 1200px) {
                                .results-grid {
                                    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
                                }
                            }

                            @media (max-width: 768px) {
                                .container {
                                    padding: 1rem;
                                }
                                
                                .results-grid {
                                    grid-template-columns: 1fr;
                                }

                                .header h1 {
                                    font-size: 2rem;
                                }

                                .ascii-art {
                                    font-size: 0.5rem;
                                }
                                
                                .stat-card {
                                    flex: 1 0 120px;
                                }
                            }

                            @media (max-width: 480px) {
                                .card-header {
                                    flex-direction: column;
                                    align-items: flex-start;
                                    gap: 0.5rem;
                                }
                                
                                .status-badge {
                                    align-self: flex-start;
                                }
                                
                                .stats-container {
                                    flex-direction: column;
                                    align-items: center;
                                }
                                
                                .stat-card {
                                    width: 100%;
                                    max-width: 250px;
                                }
                            }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <header class="header">
                                <h1>Rhino User Checker Results</h1>
                                <h2 style="color: var(--highlight); margin-bottom: 1rem;">Results for: {{ username }}</h2>
                                <div class="timestamp"><i class="far fa-clock icon"></i>Generated on {{ timestamp }}</div>
                            </header>

                            {% if results %}
                            <!-- Statistiques -->
                            <div class="stats-container">
                                <div class="stat-card">
                                    <div class="stat-value">{{ results|length }}</div>
                                    <div class="stat-label">Total Profiles</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">{{ results|selectattr("status", "equalto", "found")|list|length }}</div>
                                    <div class="stat-label">Confirmed</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">{{ results|selectattr("status", "equalto", "unsure")|list|length }}</div>
                                    <div class="stat-label">Possible</div>
                                </div>
                                <div class="stat-card">
                                    <div class="stat-value">{{ results|rejectattr("status", "equalto", "found")|rejectattr("status", "equalto", "unsure")|list|length }}</div>
                                    <div class="stat-label">With Dates</div>
                                </div>
                            </div>

                            <!-- Grille de résultats -->
                            <div class="results-grid">
                                {% for result in results %}
                                <div class="profile-card">
                                    <div class="card-header">
                                        <div class="site-info">
                                            <span class="site-name"><i class="fas fa-globe icon"></i> {{ result.name }}</span>
                                            <span class="site-category">{{ result.category }}</span>
                                        </div>
                                        
                                        <div class="status-badge {% if result.status == 'found' %}status-found{% elif result.status == 'unsure' %}status-unsure{% elif result.status != 'found' and result.status != 'unsure' %}status-date{% endif %}">
                                            {% if result.status != 'found' and result.status != 'unsure' %}
                                                <i class="fas fa-calendar-alt"></i>
                                            {% elif result.status == 'found' %}
                                                <i class="fas fa-check"></i>
                                            {% elif result.status == 'unsure' %}
                                                <i class="fas fa-question"></i>
                                            {% endif %}
                                            {{ result.status }}
                                        </div>
                                    </div>
                                    
                                    <div class="card-body">
                                        <div class="url-container">
                                            <a href="{{ result.url }}" target="_blank" class="url-link">
                                                <i class="fas fa-external-link-alt"></i>
                                                <span>{{ result.url }}</span>
                                            </a>
                                        </div>
                                        
                                        {% if result.external_links %}
                                        <div class="external-links-container">
                                            <div class="external-links-title"><i class="fas fa-link icon"></i> External Links ({{ result.external_links|length }})</div>
                                            <div class="external-links">
                                                {% for link in result.external_links %}
                                                <a href="{{ link }}" target="_blank" class="external-link" title="{{ link }}">
                                                    {{ link|truncate(30, true) }}
                                                </a>
                                                {% endfor %}
                                            </div>
                                        </div>
                                        {% endif %}
                                        
                                        {% if result.profile_info %}
                                            {% if result.profile_info.metadata %}
                                            <div class="metadata">
                                                <div class="info-title"><i class="fas fa-database icon"></i>Metadata</div>
                                                <div class="metadata-items">
                                                    {% for key, value in result.profile_info.metadata.items() %}
                                                    <div class="metadata-item">
                                                        <strong>{{ key }}:</strong> {{ value }}
                                                    </div>
                                                    {% endfor %}
                                                </div>
                                            </div>
                                            {% endif %}
                                            
                                            {% if result.profile_info.content %}
                                            <div class="content">
                                                <div class="info-title"><i class="fas fa-file-alt icon"></i>Content</div>
                                                <div class="content-items">
                                                    {% for item in result.profile_info.content %}
                                                    <div class="content-item">{{ item }}</div>
                                                    {% endfor %}
                                                </div>
                                            </div>
                                            {% endif %}
                                        {% endif %}
                                    </div>
                                </div>
                                {% endfor %}
                            </div>
                            {% else %}
                            <div class="no-results">
                                <i class="fas fa-search icon"></i> No profiles found
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
            username=username,
            is_date_status=self.is_date_status  # Ajouter la fonction au contexte
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