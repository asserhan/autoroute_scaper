#!/usr/bin/env python3
"""
ADM Scraper
1. Fetch list page
2. Extract detail links
3. Visit each detail page
4. Extract AO information
5. Save results to CSV
"""

import requests
import os
import csv
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://achats.adm.co.ma/"
LIST_URL = "https://achats.adm.co.ma/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": BASE_URL
}


def fetch_list_page(session):
    print("\nFetching list page...")
    response = session.get(LIST_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    with open("achats_page1.html", "w", encoding="utf-8") as f:
        f.write(response.text)

    print("✓ List page saved as achats_page1.html")
    return response.text


def extract_detail_links(html):
    soup = BeautifulSoup(html, "lxml")
    links = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "EntrepriseDetailsConsultation" in href:
            full_url = urljoin(BASE_URL, href)
            links.add(full_url)

    print(f"✓ Found {len(links)} detail links")
    return list(links)


def extract_ao_details(session, url):
    print(f"   → Extracting: {url}")

    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "lxml")

    data = {"URL": url}

    rows = soup.select("table tr")

    for row in rows:
        cols = row.find_all("td")
        if len(cols) == 2:
            label = cols[0].get_text(strip=True)
            value = cols[1].get_text(" ", strip=True)
            data[label] = value

    return data


def save_to_csv(data_list, filename="adm_ao_results.csv"):
    if not data_list:
        print("No data to save.")
        return

    # Collect all possible field names dynamically
    fieldnames = set()
    for item in data_list:
        fieldnames.update(item.keys())

    fieldnames = list(fieldnames)

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data_list)

    print(f"\n✓ Results saved to {filename}")


def main():
    print("=" * 80)
    print("ADM AO SCRAPER")
    print("=" * 80)

    session = requests.Session()

    try:
        # Step 1: Fetch list page
        html = fetch_list_page(session)

        # Step 2: Extract detail links
        links = extract_detail_links(html)

        if not links:
            print("⚠ No detail links found. ADM might use PRADO postback.")
            return

        # Step 3: Extract details for each AO
        all_data = []
        for link in links:
            try:
                data = extract_ao_details(session, link)
                all_data.append(data)
                time.sleep(1)  # polite delay
            except Exception as e:
                print(f"   ✗ Error extracting {link}: {e}")

        # Step 4: Save to CSV
        save_to_csv(all_data)

        print("\n✓ Scraping completed successfully.")

    except requests.exceptions.RequestException as e:
        print(f"\n✗ Network error: {e}")


if __name__ == "__main__":
    main()
