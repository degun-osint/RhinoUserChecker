from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
from typing import List, Dict, Set

class LinkAnalyzer:
    # Known social media domains
    SOCIAL_DOMAINS = {
        'twitter.com', 'facebook.com', 'linkedin.com', 'instagram.com',
        'github.com', 'gitlab.com', 'bitbucket.org', 'youtube.com',
        'medium.com', 'dev.to', 'behance.net', 'dribbble.com',
        'stackoverflow.com', 't.me', 'mastodon.social'
    }
    
    # Areas to avoid (navigation, footer, etc.)
    EXCLUDE_CONTAINERS = {
        'footer',
        'nav', 
        'navigation',
        'navbar',
        'menu',
        'sidebar',
        'header',
        'topbar',
        'bottombar',
        'copyright',
        'legal'
    }

    # Areas of interest (profile, bio, etc.)
    PROFILE_CONTAINERS = {
        'profile',
        'bio',
        'about',
        'user-info',
        'userinfo',
        'user-profile',
        'userprofile',
        'profile-info',
        'description',
        'user-description',
        'user-details',
        'personal-info',
        'account-info'
    }
    
    EXCLUDE_KEYWORDS = {
        # System and legal pages
        'privacy', 'legal', 'terms', 'policy', 'cookie',
        'about', 'contact', 'help', 'support',
        'documentation', 'docs', 'guidelines',
        'static', 'api', 'enterprise', 'showcase', 'policie',
        'advertising', 'welcome',
        
        # Marketing and sharing
        'share', 'sharer', 'sharing', 'newsletter',
        'subscribe', 'subscription', 'marketing',
        
        # Authentication and account
        'login', 'signin', 'signup', 'register',
        'authentication', 'password', 'forgot',
        
        # Commerce
        'shop', 'store', 'pricing', 'payment',
        'checkout', 'cart', 'billing',
        
        # Miscellaneous
        'sitemap', 'search', 'tag', 'category',
        'feed', 'rss', 'download', 'uploads',
        'status', 'stats', 'analytics', 'envato', 'placeit'
    }

    def __init__(self, html_content: str, base_url: str):
        self.soup = BeautifulSoup(html_content, 'html.parser')
        self.base_url = base_url
        parsed_base = urlparse(base_url)
        self.base_domain = parsed_base.netloc.lower()
        
        # Extract the main domain name
        domain_parts = self.base_domain.split('.')
        if domain_parts[0] == 'www':
            domain_parts = domain_parts[1:-1]  # Remove www and tld
        else:
            domain_parts = domain_parts[1:-1] if len(domain_parts) > 2 else domain_parts[:-1]  # Remove tld and subdomain if present
            
        self.domain_name = '.'.join(domain_parts)  # For cases with multiple subdomains, keep all

    def _should_exclude_link(self, url: str) -> bool:
        """Check if a link should be excluded from results."""
        url_lower = url.lower()
        
        # If domain name appears anywhere in the URL, exclude it
        if self.domain_name in url_lower:
            return True
            
        # If URL contains an excluded keyword
        if any(keyword.lower() in url_lower for keyword in self.EXCLUDE_KEYWORDS):
            return True
            
        return False

    def _is_in_excluded_container(self, element) -> bool:
        """Check if element is in an excluded container.
        Partial matching is used, so 'footer' will match 'global-footer', 'footer-wrapper', etc."""
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
                    
            # Check tag names (exact match as these are standard HTML tags)
            if parent.name and parent.name.lower() in self.EXCLUDE_CONTAINERS:
                return True
                
        return False

    def _is_in_profile_container(self, element) -> bool:
        """Check if element is in a profile container."""
        for parent in element.parents:
            # Check IDs
            if parent.get('id') and any(prof in parent.get('id').lower() for prof in self.PROFILE_CONTAINERS):
                return True
            # Check classes
            if parent.get('class'):
                if any(prof in ' '.join(parent.get('class')).lower() for prof in self.PROFILE_CONTAINERS):
                    return True
        return False

    def _is_valid_external_link(self, url: str) -> bool:
        """Check if a link is a valid external link."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Ignore empty links or links to the same domain
            if not domain or domain == self.base_domain:
                return False
                
            # If it's a link to a known social media profile, keep it
            social_profile_indicators = ['/user/', '/users/', '/profile/', '@', '/u/', '/channel/']
            if any(social_domain in domain for social_domain in self.SOCIAL_DOMAINS):
                if any(indicator in url.lower() for indicator in social_profile_indicators):
                    # But still check if source domain name isn't present
                    return not self._should_exclude_link(url)

            # Exclude based on defined criteria
            if self._should_exclude_link(url):
                return False

            # Check for URLs that look like user profiles
            user_profile_patterns = [
                r'/[~@][\w-]+/?$',
                r'/users?/[\w-]+/?$',
                r'/profiles?/[\w-]+/?$',
                r'/members?/[\w-]+/?$',
                r'/channel/[\w-]+/?$',
                r'/commissions/[\w-]+/?$'
            ]
            
            if any(re.search(pattern, url) for pattern in user_profile_patterns):
                return True

            return True  # If we get here, the link has passed all filters

        except Exception:
            return False

    def analyze(self) -> List[str]:
        """Analyze HTML to find relevant external links."""
        links = set()
        for a_tag in self.soup.find_all('a', href=True):
            href = a_tag['href']
            if href.startswith(('http://', 'https://')):
                full_url = href
            else:
                full_url = urljoin(self.base_url, href)
            
            if self._is_valid_external_link(full_url):
                links.add(full_url)

        # Clean and normalize URLs
        cleaned_links = []
        for link in links:
            # Remove common tracking parameters
            cleaned_url = re.sub(r'\?.*$', '', link)
            # Remove trailing slash
            cleaned_url = re.sub(r'/$', '', cleaned_url)
            cleaned_links.append(cleaned_url)

        return sorted(list(set(cleaned_links)))  # Remove duplicates and sort

def analyze_links(html_content: str, base_url: str) -> List[str]:
    """
    Utility function to analyze links on a page.
    
    Args:
        html_content (str): The HTML content to analyze
        base_url (str): The base URL for resolving relative links
        
    Returns:
        List[str]: List of external links found
    """
    analyzer = LinkAnalyzer(html_content, base_url)
    return analyzer.analyze()