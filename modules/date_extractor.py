import re
from datetime import datetime
from typing import Optional

def extract_profile_date(html_content: str, metadata: dict, site_name: str = "") -> Optional[str]:
    """
    Extraire la date de création du profil à partir du contenu HTML ou des métadonnées.
    
    Args:
        html_content (str): Le contenu HTML de la page
        metadata (dict): Les métadonnées extraites du profil
        site_name (str): Le nom du site pour appliquer des règles spécifiques
        
    Returns:
        Optional[str]: La date de création formatée, ou None si aucune date n'est trouvée
    """
    # Exclure certains sites ou patterns spécifiques
    if site_name.lower() == "behance" and "created_on" in html_content:
        return None
        
    # Vérifier si le contenu provient d'une balise link rel
    has_link_rel_date = "<link rel=" in html_content and re.search(r'<link\s+rel=["\'].*?date.*?["\']', html_content)
    
    # Liste des indicateurs fiables qui doivent précéder une date pour qu'elle soit considérée comme date de création
    date_indicators = [
        r'joined', r'member since', r'est\.', r'established',
        r'user since', r'account created', r'registration date',
        r'created on', r'date joined', r'created at', r'profile created'
    ]
    
    # Motifs de recherche pour les dates de création de profil
    # Maintenant, chaque pattern inclut un indicateur fiable suivi d'une date
    join_patterns = [
        # Format Twitter: "Joined September 2023"
        r'[Jj]oined\s+(\w+\s+\d{4})',
        
        # Format "Member since: Jan 2022" ou "Member since Jan 2022"
        r'[Mm]ember\s+[Ss]ince:?\s+(\w+\s+\d{4})',
        
        # Format "Joined on" ou "Created on": "Joined on 12/05/2021"
        r'(?:[Jj]oined|[Cc]reated)(?:\s+on)?\s+(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})',
        
        # Format "Registration date: 2022-03-15"
        r'[Rr]egistration\s+[Dd]ate:?\s+(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})',
        
        # Format "Account created: March 15, 2021"
        r'[Aa]ccount\s+[Cc]reated:?\s+(\w+\s+\d{1,2},?\s+\d{4})',
        
        # Format "User since 2021"
        r'[Uu]ser\s+[Ss]ince\s+(\d{4})',
        
        # Format "Est. YYYY" (popularisé par GitHub)
        r'[Ee]st\.\s+(\d{4})',
        
        # Format "Created: YYYY-MM-DD"
        r'[Cc]reated:?\s+(\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2})',
    ]
    
    # Rechercher d'abord dans les métadonnées
    if metadata:
        for key, value in metadata.items():
            if isinstance(value, str) and any(kw in key.lower() for kw in ['joined', 'since', 'registration', 'created']):
                for pattern in join_patterns:
                    match = re.search(pattern, value)
                    if match:
                        # Si on trouve une date dans les métadonnées et qu'elle est précédée d'un indicateur fiable
                        if has_link_rel_date:
                            # Vérifier que la date n'est pas dans une balise link rel
                            link_match = re.search(r'<link\s+rel=["\'].*?\b' + re.escape(match.group(1)) + r'\b.*?["\']', html_content, re.IGNORECASE)
                            if link_match:
                                continue  # Ignorer cette correspondance
                        return match.group(1)
    
    # Puis rechercher dans le contenu HTML
    for pattern in join_patterns:
        match = re.search(pattern, html_content)
        if match:
            # Si on a détecté une balise link rel, vérifier que la date n'est pas dedans
            if has_link_rel_date:
                link_match = re.search(r'<link\s+rel=["\'].*?\b' + re.escape(match.group(1)) + r'\b.*?["\']', html_content, re.IGNORECASE)
                if link_match:
                    continue  # Ignorer cette correspondance
            return match.group(1)
    
    return None

def normalize_date(date_str: str) -> str:
    """
    Tenter de normaliser le format de date pour un affichage cohérent.
    Cette fonction est simple et peut être améliorée pour gérer plus de formats.
    
    Args:
        date_str (str): La chaîne de date extraite
        
    Returns:
        str: La date normalisée, ou la chaîne originale si impossible à normaliser
    """
    # Pour l'instant, simplement nettoyer la chaîne
    date_str = date_str.strip()
    
    # Supprimer les virgules pour simplifier
    date_str = date_str.replace(',', '')
    
    # Pour une implémentation plus robuste, on pourrait tenter de parser la date
    # avec datetime.strptime() et la reformater selon un format standard
    
    return date_str