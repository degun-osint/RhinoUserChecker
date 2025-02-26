# 🦏 RhinoUserChecker (RPUC)

** PLEASE BE AWARE THAT THIS IS NOT A PRODUCTION VERSION AND SHOULD BE USED WITH CAUTION **

A Python-based OSINT tool that helps you find usernames across multiple platforms and extract profile information. Built on top of the WhatsMyName project's data, RPUC adds advanced profile extraction and external link analysis capabilities.

## 🌟 Features

- **Multi-platform Search**: Search for usernames across hundreds of social media platforms and websites thanks to WhatMyName JSON file
- **Profile Information Extraction**: Automatically extract user profile information, bios, and metadata
- **Profile creation date**: Attempt to find account creation date
- **External Link Analysis**: Discover related profiles through external link analysis
- **Smart Rate Limiting**: Built-in proxy support and smart rate limiting to avoid blocking
- **Rich Console Output**: Real-time progress tracking and beautiful console output using Rich
- **HTML or CSV Report Generation**: Generate detailed HTML or CSV reports with all findings
- **International Platform Support**: Special handling for international platforms (Russian, Chinese, Japanese, etc.)

## Discussion

You can join the OSCAR ZULU discord server to discuss about this tool : https://discord.gg/4REgJzn4NG

## 📋 Requirements

```text
Python 3.8+
See requirements.txt for full dependencies
```

## 🚀 Installation

1. Clone the repository:
```bash
git clone https://github.com/degun-osint/RhinoUserChecker
cd RhinoUserChecker
```

2. Create a virtual environment and activate it:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

RPUC uses environment variables for configuration. Create a `.env` file in the root directory with:

```env
WMN_JSON_URL=https://raw.githubusercontent.com/WebBreacher/WhatsMyName/main/wmn-data.json
PROXY_URL=http://127.0.0.1:8000/proxy
```
By default, the script uses a forked version of WMN JSON.

## 🎮 Usage

Start the tool by running:

```bash
python run.py
```

The tool will:
1. Download the latest site data from WhatsMyName project
2. Prompt you for a username to search
3. Search across hundreds of platforms
4. Generate an HTML or a CSV report with findings

## 📊 Output

RPUC generates two types of output:
- Real-time console output with progress tracking
- Detailed HTML or CSV report containing:
  - Found profiles with links
  - Status (found = good chance profile exists, unsure = good http [200] code when a 404 was expected if profile does not exists, but can't confirm the profile)
  - Extracted profile information
  - Discovered external links
  - Metadata from profiles

## 🏗️ Project Structure

```
rpuc/
├── run.py              # Main entry point
├── modules/
│   ├── proxy.py        # Proxy server for rate limiting
│   ├── rpuc.py         # Core functionality
│   ├── date_extractor.py  # date search
│   ├── link_analyzer.py # External link analysis
│   └── profile_extractor.py # Profile information extraction
├── data/               # Data storage
└── results/            # Generated reports
```

## 🔧 Advanced Usage

### Custom Headers

RPUC supports custom headers for different domains/regions. Edit the `DOMAIN_PATTERNS` in `proxy.py` to add more patterns.

### Proxy Configuration

By default, RPUC runs its own proxy server for rate limiting. You can configure an external proxy by modifying the `PROXY_URL` in your `.env` file.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📜 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE.txt) file for details.

## 🙏 Credits

- Based on the [WhatsMyName Project](https://github.com/WebBreacher/WhatsMyName)
- Built with:
  - [FastAPI](https://fastapi.tiangolo.com/)
  - [Rich](https://rich.readthedocs.io/)
  - [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)
  - [aiohttp](https://docs.aiohttp.org/)

## ⚠️ Disclaimer

This tool is for educational purposes only. Be mindful of the platforms' terms of service and use responsibly.

## Author

DEGUN (https://github.com/degun-osint)