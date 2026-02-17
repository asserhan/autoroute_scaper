#!/usr/bin/env python3

import requests
import csv
import json
import time
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from collections import OrderedDict

BASE_URL = "https://achats.adm.co.ma/"
LIST_URL = "https://achats.adm.co.ma/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": BASE_URL,
    "Content-Type": "application/x-www-form-urlencoded"
}


def clean_text(text):
    """Remove extra whitespace and normalize text"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_tender_from_card(card_div):
    """Extract all information from a single tender card"""
    data = OrderedDict()
    
    # Extract URL
    onclick = card_div.get('onclick', '')
    if 'location.href=' in onclick:
        url = onclick.split('location.href="')[1].split('"')[0]
        data['URL'] = urljoin(BASE_URL, url)
    
    # Extract Référence
    ref_span = card_div.find('span', id=re.compile(r'.*referencem'))
    if ref_span:
        data['Référence'] = clean_text(ref_span.get_text())
    
    # Extract Type (AOO, AOR, etc.) from verticalText
    vertical_text = card_div.find('span', class_='verticalText')
    if vertical_text:
        type_span = vertical_text.find('span')
        if type_span:
            data['Type'] = clean_text(type_span.get_text())
            data['Type (Description)'] = type_span.get('title', '')
    
    # Extract Objet
    objet_div = card_div.find('div', class_='p-objet')
    if objet_div:
        strong = objet_div.find('strong')
        if strong:
            strong.extract()
        data['Objet'] = clean_text(objet_div.get_text())
    
    # Extract Entité
    title_card = card_div.find('div', class_='title p-card')
    if title_card:
        strong = title_card.find('strong')
        text = clean_text(title_card.get_text())
        if strong and 'Entité' in text:
            entite = text.replace('Entité', '').replace(':', '').strip()
            data['Entité'] = entite
    
    # Extract Estimation
    estim_span = card_div.find('span', class_='estim-mad')
    if estim_span:
        estimation = clean_text(estim_span.get_text())
        if estimation:
            data['Estimation (en DH)'] = estimation
    
    # Extract Date limite de remise des plis
    limita_cards = card_div.find_all('div', class_='limita p-card')
    found_date = False
    
    for i, limita_card in enumerate(limita_cards):
        text = clean_text(limita_card.get_text())
        
        # Check if this is the "Date limite de remise des plis" label
        if "Date limite de remise des plis" in text and not found_date:
            found_date = True
            # The next limita p-card should contain the date and time
            if i + 1 < len(limita_cards):
                next_card = limita_cards[i + 1]
                
                # Look for date and time in the next card
                date_parts = []
                
                # Find all divs with vertical-align: inherit style
                date_divs = next_card.find_all('div', style=re.compile(r'vertical-align'))
                for date_div in date_divs:
                    # Look for spans with display style
                    date_span = date_div.find('span', style=re.compile(r'display'))
                    if date_span:
                        date_text = clean_text(date_span.get_text())
                        if date_text and date_text not in date_parts:
                            date_parts.append(date_text)
                
                if date_parts:
                    data['Date et heure limite de remise des plis'] = ' '.join(date_parts)
                    break
    
    # Extract Lieu d'exécution
    lieu_cards = card_div.find_all('div', class_='limita p-card')
    for i, lieu_card in enumerate(lieu_cards):
        text = clean_text(lieu_card.get_text())
        if "Lieu d'exécution" in text:
            # The next div should contain the location
            if i + 1 < len(lieu_cards):
                next_card = lieu_cards[i + 1]
                # Extract visible location text
                location_text = []
                for br in next_card.find_all('br'):
                    if br.previous_sibling and isinstance(br.previous_sibling, str):
                        loc = clean_text(br.previous_sibling)
                        if loc:
                            location_text.append(loc)
                
                # Also check for text in info-bulle (full location list)
                info_bulle = next_card.find('div', class_='info-bulle')
                if info_bulle:
                    full_location = clean_text(info_bulle.get_text())
                    if full_location:
                        data['Lieu d\'exécution (complet)'] = full_location
                
                if location_text:
                    data['Lieu d\'exécution'] = ', '.join(location_text[:3])  # First 3 locations
    
    # Extract certification/signature requirement
    cert_img = card_div.find('img', class_='certificat')
    if cert_img:
        data['Type de réponse électronique'] = cert_img.get('title', '')
    
    return data


def fetch_list_page(session):
    """Fetch the tender list page with 500 results per page"""
    print("Fetching list page with 500 results per page...")
    
    # Payload to set page size to 500
    payload = {
        'ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop': '500',
        'ctl0$CONTENU_PAGE$resultSearch$listePageSizeBottom': '500',
    }
    
    # First, make a GET request to get the initial page and extract PRADO_PAGESTATE
    response = session.get(LIST_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    
    # Parse the page to get PRADO_PAGESTATE
    soup = BeautifulSoup(response.text, "lxml")
    pagestate_input = soup.find('input', {'name': 'PRADO_PAGESTATE'})
    
    if pagestate_input:
        pagestate = pagestate_input.get('value', '')
        print(f"  ✓ Got PRADO_PAGESTATE (length: {len(pagestate)})")
        
        # Now make a POST request with the pagestate and page size
        payload['PRADO_PAGESTATE'] = pagestate
        payload['PRADO_POSTBACK_TARGET'] = 'ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop'
        
        print("  Requesting 500 results...")
        response = session.post(LIST_URL, data=payload, headers=HEADERS, timeout=30)
        response.raise_for_status()
        
        return response.text
    else:
        print("  ⚠ Could not find PRADO_PAGESTATE, using initial page")
        return response.text


def extract_all_tenders(html):
    """Extract all tenders from the list page"""
    soup = BeautifulSoup(html, "lxml")
    
    # Find all tender cards - only the ones with onclick attribute (the main cards)
    tender_cards = soup.find_all('div', class_='contentColumn', onclick=True)
    
    print(f"✓ Found {len(tender_cards)} tender cards")
    
    all_tenders = []
    seen_refs = set()  # Track references to avoid duplicates
    
    for i, card in enumerate(tender_cards, 1):
        print(f"  Extracting tender {i}/{len(tender_cards)}...")
        tender_data = extract_tender_from_card(card)
        
        # Only add if we have a reference and haven't seen it before
        if tender_data and 'Référence' in tender_data:
            ref = tender_data['Référence']
            if ref not in seen_refs:
                seen_refs.add(ref)
                all_tenders.append(tender_data)
            else:
                print(f"    ⚠ Skipping duplicate: {ref}")
        elif tender_data and 'URL' in tender_data:
            # If no reference but has URL, still add it
            all_tenders.append(tender_data)
    
    return all_tenders


def get_all_fieldnames(data_list):
    """Collect all unique field names from all records"""
    all_fields = OrderedDict()
    
    for data in data_list:
        for key in data.keys():
            all_fields[key] = None
    
    # Ensure URL is first
    fieldnames = ["URL"]
    for key in all_fields.keys():
        if key != "URL":
            fieldnames.append(key)
    
    return fieldnames


def save_to_csv(data_list, filename="adm_tenders.csv"):
    """Save tender data to CSV"""
    if not data_list:
        print("No data found.")
        return

    fieldnames = get_all_fieldnames(data_list)

    print(f"\n✓ Total unique fields found: {len(fieldnames)}")
    print(f"  📊 Fields extracted:")
    for field in fieldnames:
        print(f"     - {field}")

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for data in data_list:
            row = {field: data.get(field, "") for field in fieldnames}
            writer.writerow(row)

    print(f"\n✓ CSV data saved to {filename}")


def save_to_json(data_list, filename="adm_tenders.json"):
    """Save tender data to JSON with nice formatting"""
    if not data_list:
        print("No data found.")
        return

    # Convert OrderedDict to regular dict for JSON serialization
    json_data = []
    for tender in data_list:
        json_data.append(dict(tender))
    
    # Create structured JSON output
    output = {
        "metadata": {
            "total_tenders": len(data_list),
            "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": LIST_URL
        },
        "tenders": json_data
    }
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"✓ JSON data saved to {filename}")


def main():
    print("=" * 70)
    print("ADM TENDER SCRAPER - LIST PAGE EXTRACTION")
    print("=" * 70)

    session = requests.Session()

    try:
        html = fetch_list_page(session)
        
        # Parse to check total number of results
        soup = BeautifulSoup(html, "lxml")
        nombre_element = soup.find('span', id='ctl0_CONTENU_PAGE_resultSearch_nombreElement')
        
        total_results = 0
        if nombre_element:
            total_results = int(nombre_element.get_text().strip())
            print(f"\n📊 Total results found: {total_results}")
        
        tenders = extract_all_tenders(html)

        if not tenders:
            print("⚠ No tenders found.")
            return
        
        # Check if we need to fetch more pages
        if total_results > 500:
            print(f"\n⚠ Warning: There are {total_results} total results.")
            print(f"   Currently fetched: {len(tenders)} tenders")
            print(f"   Note: This script fetches up to 500 results per page.")
            print(f"   To get all results, you may need to implement multi-page fetching.")

        # Save to both CSV and JSON
        save_to_csv(tenders, "adm_tenders.csv")
        save_to_json(tenders, "adm_tenders.json")

        print("\n" + "=" * 70)
        print(f"✓ Scraping completed successfully.")
        print(f"✓ Total tenders extracted: {len(tenders)}")
        print(f"✓ Output files:")
        print(f"   - adm_tenders.csv (spreadsheet format)")
        print(f"   - adm_tenders.json (structured JSON)")
        print("=" * 70)

    except requests.exceptions.RequestException as e:
        print(f"Network error: {e}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()