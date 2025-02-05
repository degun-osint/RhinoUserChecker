from bs4 import BeautifulSoup
from typing import Dict, Set, List
from urllib.parse import urlparse
import json
import re

class ProfileExtractor:
    # Profile related containers and classes
    PROFILE_CONTAINERS = {
        # Common profile containers
        'profile',
        'bio',
        'about',
        'description',
        'user-info',
        'user-profile',
        'userprofile',
        'user-bio',
        'userbio',
        'author-info',
        'author-bio',
        'biography',
        
        # Social media specific
        'profile-header',
        'profile-card',
        'profile-info',
        'profile-details',
        'user-details',
        'personal-info',
        'account-info',
        
        # Content descriptions
        'user-description',
        'creator-info',
        'artist-info',
        'member-info'
    }
    
    # Common metadata fields that might contain profile information
    METADATA_FIELDS = {
        'description',
        'og:description',
        'profile:username',
        'profile:first_name',
        'profile:last_name',
        'author',
        'twitter:description',
        'article:author',
        'profile:gender',
        'profile:location'
    }
    
    # Common UI elements to ignore
    UI_ELEMENTS = {
        'menu', 'navigation', 'nav', 'search', 'button',
        'dialog', 'modal', 'popup', 'tooltip', 'dropdown',
        'tab', 'menu-item', 'sidebar', 'widget', 'footer'
    }
    
    # Content to exclude (similar to link analyzer)
    EXCLUDE_CONTAINERS = {
        'footer',
        'header',
        'nav',
        'navigation',
        'menu',
        'sidebar',
        'copyright',
        'legal',
        'advertisement',
        'cookie',
        'popup',
        'stats',
        'style',
        'script'
    }

    def __init__(self, html_content: str, base_url: str):
        """Initialize the ProfileExtractor."""
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self.base_url = base_url
        
        # Extract domain name for filtering
        parsed_base = urlparse(base_url)
        self.base_domain = parsed_base.netloc.lower()
        domain_parts = self.base_domain.split('.')
        if domain_parts[0] == 'www':
            domain_parts = domain_parts[1:-1]
        else:
            domain_parts = domain_parts[1:-1] if len(domain_parts) > 2 else domain_parts[:-1]
        self.domain_name = '.'.join(domain_parts)

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text."""
        # Remove multiple spaces and newlines
        text = ' '.join(text.split())
        # Remove common UI text patterns
        text = re.sub(r'(Follow|Message|Subscribe|Share|Like|Comment|Post|View|Open|Close|Toggle|Click|Tap)\s*', '', text, flags=re.IGNORECASE)
        return text.strip()

    def _is_meaningful_text(self, text: str) -> bool:
        """Check if text contains meaningful information."""
        # Minimum length check
        if len(text) < 3:
            return False
            
        # Check if text is just a single common word
        common_words = {'menu', 'home', 'about', 'contact', 'search', 'login', 'signup'}
        if text.lower() in common_words:
            return False
            
        # Check if text is just numbers
        if text.replace(',', '').replace('.', '').isdigit():
            return False
            
        # Check if text is just a common UI element
        if text.lower() in self.UI_ELEMENTS:
            return False
            
        return True

    def _is_in_excluded_container(self, element) -> bool:
        """Check if element is in a container that should be excluded."""
        for parent in element.parents:
            # Check IDs
            if parent.get('id'):
                parent_id = parent.get('id').lower()
                if any(exc in parent_id or parent_id in exc for exc in self.EXCLUDE_CONTAINERS):
                    return True
                    
            # Check classes
            if parent.get('class'):
                parent_classes = ' '.join(parent.get('class')).lower()
                if any(exc in parent_classes for exc in self.EXCLUDE_CONTAINERS):
                    return True
                    
            # Check tag names
            if parent.name and parent.name.lower() in self.EXCLUDE_CONTAINERS:
                return True
                
        return False

    def _extract_from_metadata(self) -> Dict[str, str]:
        """Extract profile information from metadata tags."""
        metadata = {}
        
        # Extract from standard meta tags
        for meta in self.soup.find_all('meta'):
            name = meta.get('name', meta.get('property', '')).lower()
            if name in self.METADATA_FIELDS:
                content = self._clean_text(meta.get('content', ''))
                if content and not self._should_exclude_content(content):
                    metadata[name] = content
        
        # Extract from JSON-LD
        for script in self.soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if data.get('@type') in ['Person', 'Profile']:
                        for key, value in data.items():
                            if isinstance(value, str):
                                cleaned_value = self._clean_text(value)
                                if cleaned_value and not self._should_exclude_content(cleaned_value):
                                    metadata[key] = cleaned_value
            except (json.JSONDecodeError, AttributeError):
                continue
        
        return metadata

    def _should_exclude_content(self, text: str) -> bool:
        """Check if content should be excluded."""
        return self.domain_name.lower() in text.lower()

    def _extract_from_html(self) -> Set[str]:
        """Extract profile information from HTML content."""
        profile_texts = set()
        seen_texts = set()

        # First, get all text elements
        for element in self.soup.find_all(text=True):
            # Check if element is inside excluded container like footer FIRST
            if self._is_in_excluded_container(element):
                continue  # Skip this element and all its content

            # Only then check if it's in a profile container
            parent_element = element.parent
            if any(ptn in str(parent_element.get('class', [])).lower() or 
                ptn in str(parent_element.get('id', '')).lower() 
                for ptn in self.PROFILE_CONTAINERS):
                
                text = self._clean_text(element.string)
                if (text and 
                    text not in seen_texts and 
                    len(text) >= 3):
                    
                    profile_texts.add(text)
                    seen_texts.add(text)

        return profile_texts

    def extract(self) -> Dict[str, List[str]]:
        """Extract all profile information from the page."""
        metadata = self._extract_from_metadata()
        content = sorted(list(self._extract_from_html()))  # Convert set to sorted list
        
        return {
            'metadata': metadata,
            'content': content
        }

def extract_profile_info(html_content: str, base_url: str) -> Dict[str, List[str]]:
    """Utility function to extract profile information from a page."""
    extractor = ProfileExtractor(html_content, base_url)
    return extractor.extract()