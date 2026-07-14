import sys
import os
import json
import hashlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.config import settings
from core.database import fetchStoredHash
from scraper.playwrightEngine import PlaywrightBrowser
from scraper.crawlerUtils import shouldProcessUrl, chunkText

def computeContentHash(textInput):
    return hashlib.sha256(textInput.encode('utf-8')).hexdigest()

def executeHardScrape():
    print("==================================================")
    print(" RUNNING STANDALONE HARD CRAWLER & CHUNKER")
    print("==================================================")
    
    seeds = [
        # Core Company Pages
        "https://netsoltech.com",
        "https://netsoltech.com/about-us/board-of-directors",
        "https://netsoltech.com/contact-us",
        
        # Main Offerings & Services
        "https://netsoltech.com/services",
        "https://netsoltech.com/marketplace",
        
        # Specific Solutions
        "https://netsoltech.com/services/information-security",
        "https://netsoltech.com/services/ai-ml-services-and-solutions",
        "https://netsoltech.com/services/generative-ai",
        "https://netsoltech.com/services/policy-strategy-consulting",
        "https://netsoltech.com/services/emerging-technologies",
        "https://netsoltech.com/services/cloud-services",
        "https://netsoltech.com/services/data-engineering",
        "https://netsoltech.com/solutions/equipment-finance",
        
        # Specific Products
        "https://netsoltech.com/insights",
        "https://netsoltech.com/about-us/why-netsol",
        "https://ir.netsoltech.com/?_gl=1*497xcy*_gcl_au*MTg1MTk0NDg0NC4xNzgzNTc3NDI4",
        
        # Strategic / Consulting
        "https://netsoltech.com/about-us/management-team"
    ]
    
    queue = list(seeds)
    visited = set()
    scrapedResults = []
    maxPages = 50
    
    with PlaywrightBrowser() as scraper:
        while queue and len(visited) < maxPages:
            url = queue.pop(0)
            if url in visited:
                continue
                
            visited.add(url)
            print(f"\n[{len(visited)}/{maxPages}] Targeting Endpoint: {url}")
            
            try:
                htmlContent, pageTitle, statusCode = scraper.fetch_page(url)
                if statusCode != 200:
                    print(f"[SKIP] Status code {statusCode}. Moving to next target.")
                    scrapedResults.append({
                        "url": url,
                        "status": "http_error",
                        "status_code": statusCode,
                        "title": None,
                        "content": None,
                        "hash": None,
                        "chunks": [],
                        "error": f"HTTP status code {statusCode}"
                    })
                    continue
                    
                soupObj = BeautifulSoup(htmlContent, 'html.parser')
                
                # Discover internal links to crawl
                anchors = soupObj.find_all('a', href=True)
                for anchor in anchors:
                    href = anchor['href']
                    absoluteUrl = urljoin(url, href).split('#')[0]
                    if shouldProcessUrl(absoluteUrl) and absoluteUrl not in visited and absoluteUrl not in queue:
                        queue.append(absoluteUrl)
                        
                # Remove cookie consent banners and popup dialogs
                for attr_name in ["id", "class"]:
                    for tag in soupObj.find_all(attrs={attr_name: lambda x: x and any(k in str(x).lower() for k in ["cookie", "cookiebot", "consent"])}):
                        tag.decompose()
                        
                # Extract and clean text content
                for garbageTag in soupObj(["script", "style", "nav", "footer", "header"]):
                    garbageTag.decompose()
                    
                cleanText = " ".join(soupObj.get_text().split())
                newHash = computeContentHash(cleanText)
                
                # Compare to relational SQLite record
                oldHash = fetchStoredHash(url)
                status = "updated" if oldHash != newHash else "skipped"
                
                if status == "skipped":
                    print("-> Content matches stored hash perfectly. Marked as skipped.")
                else:
                    print("-> New/modified content identified. Marked as updated.")
                    
                # Split content into semantic overlapping chunks
                chunks = chunkText(cleanText, pageTitle)
                
                scrapedResults.append({
                    "url": url,
                    "status": status,
                    "title": pageTitle,
                    "content": cleanText,
                    "hash": newHash,
                    "chunks": chunks,
                    "error": None
                })
                
            except Exception as error:
                print(f"[ERROR] Failed to process {url}: {str(error)}")
                scrapedResults.append({
                    "url": url,
                    "status": "failed",
                    "title": None,
                    "content": None,
                    "hash": None,
                    "chunks": [],
                    "error": str(error)
                })
                
    # Write all accumulated staged results to JSON file
    outputPath = "data/scraped_chunks.json"
    os.makedirs(os.path.dirname(outputPath), exist_ok=True)
    try:
        with open(outputPath, "w", encoding="utf-8") as jsonFile:
            json.dump(scrapedResults, jsonFile, indent=2, ensure_ascii=False)
        print(f"\nScraping and chunking complete. Results saved to {outputPath}")
        print("Please review the staging file, then run 'python commitEmbeddings.py' to load.")
    except Exception as saveError:
        print(f"\n[ERROR] Failed to save scraping results: {str(saveError)}")
        
    print("\nStandalone hard crawling and chunking process finalized.")

if __name__ == "__main__":
    executeHardScrape()