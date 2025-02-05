#!/usr/bin/env python3
# modules/proxy.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
from urllib.parse import urlparse
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain-specific header configurations
DOMAIN_PATTERNS = {
    '.ru': {
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    },
    '.pl': {
        'Accept-Language': 'pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/120.0'
    },
    '.jp': {
        'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15'
    },
    '.cn': {
        'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
    },
    'behance.net': {
        'Accept-Language': 'en-US,en;q=0.9',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Referer': 'https://www.behance.net/'
    },
    'community': {
        'Accept': 'application/activity+json',
        'User-Agent': 'Mozilla/5.0 (compatible; SocialMediaBot/1.0)'
    },
    'mastodon': {
        'Accept': 'application/activity+json',
        'User-Agent': 'Mozilla/5.0 (compatible; SocialMediaBot/1.0)'
    }
}

# Default headers
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
}

@app.get("/proxy")
async def proxy(url: str):
    if not url:
        raise HTTPException(status_code=400, detail='URL parameter is required')
    
    domain = urlparse(url).netloc.replace('www.', '')
    
    # Build headers
    headers = DEFAULT_HEADERS.copy()
    for pattern, pattern_headers in DOMAIN_PATTERNS.items():
        if pattern in domain:
            headers.update(pattern_headers)
            break

    try:
        async with httpx.AsyncClient(verify=False, timeout=25.0) as client:
            # First request without following redirects
            response = await client.get(
                url,
                headers=headers,
                follow_redirects=False
            )
            
            initial_status_code = response.status_code
            
            # If redirect, follow with a new request
            if 300 <= initial_status_code < 400:
                response = await client.get(
                    url,
                    headers=headers,
                    follow_redirects=True
                )

            # Build response
            result = {
                'status': {
                    'http_code': response.status_code,
                    'initial_http_code': initial_status_code,
                    'headers': dict(response.headers)
                },
                'contents': response.text,
                'url': str(response.url)
            }
            
            # Add redirect history if present
            if response.history:
                result['status']['redirect_history'] = [
                    {
                        'url': str(r.url),
                        'status_code': r.status_code,
                        'headers': dict(r.headers)
                    }
                    for r in response.history
                ]
            
            return result

    except httpx.RequestError as e:
        error_details = {
            'message': str(e),
            'code': type(e).__name__,
            'url': url
        }
        
        if isinstance(e, httpx.TimeoutException):
            return {
                'error': error_details,
                'status': {'http_code': 504}
            }

        return {
            'error': error_details,
            'status': {'http_code': 500}
        }

if __name__ == "__main__":
    import uvicorn
    import logging
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")