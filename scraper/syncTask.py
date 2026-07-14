import sys
import asyncio
import hashlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from core.database import fetchStoredHash, updateStoredHash
from core.chromaClient import upsertVectorChunks
from core.llmClient import embeddingEngine
from scraper.playwrightEngine import PlaywrightBrowser
from scraper.crawlerUtils import shouldProcessUrl, chunkText

def computeContentHash(textInput):
    return hashlib.sha256(textInput.encode('utf-8')).hexdigest()

def executeDeltaSync():
    """
    Runs automatically on live server startup. Performs an instantaneous 
    hash check and skips heavy API embedding operations if data matches.
    """
    # FIX: Correctly set the global loop policy for this thread before Playwright initializes
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception as e:
            print(f"[Warning] Failed to set ProactorEventLoopPolicy on background thread: {e}")

    print("Initiating background delta sync for Netsol website...")
    
    seeds = [
        # Core Company Pages
        "https://netsoltech.com",
        "https://netsoltech.com/about-us",
        "https://netsoltech.com/contact-us",
        
        # Main Offerings & Services
        "https://netsoltech.com/services",
        "https://netsoltech.com/marketplace",
        
        # Specific Solutions
        "https://netsoltech.com/solutions/asset-finance",
        "https://netsoltech.com/solutions/equipment-finance",
        "https://netsoltech.com/solutions/auto-finance",
        
        # Specific Products
        "https://netsoltech.com/products/digital-retail",
        "https://netsoltech.com/products/portals/broker-portal",
        "https://netsoltech.com/products/portals/retail-portal",
        "https://netsoltech.com/products/portals/dealer-portal",
        
        # Strategic / Consulting
        "https://netsoltech.com/aws-consulting",
        "https://netsoltech.com/innovation-lab"
    ]
    
    queue = list(seeds)
    visited = set()
    updatedPagesCount = 0
    maxPages = 50
    
    with PlaywrightBrowser() as scraper:
        while queue and len(visited) < maxPages:
            url = queue.pop(0)
            if url in visited:
                continue
                
            visited.add(url)
            
            try:
                htmlContent, pageTitle, statusCode = scraper.fetch_page(url)
                if statusCode != 200:
                    continue
                    
                soupObj = BeautifulSoup(htmlContent, 'html.parser')
                
                # Discover links
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
                        
                for garbageTag in soupObj(["script", "style", "nav", "footer", "header"]):
                    garbageTag.decompose()
                    
                cleanText = " ".join(soupObj.get_text().split())
                
                # Safeguard: Skip incomplete crawls (e.g., cookie consent only, dynamic content missing)
                if len(cleanText) < 300:
                    print(f"  [WARNING] Crawled content for {url} is too short ({len(cleanText)} chars). Skipping to avoid database corruption.")
                    continue
                    
                newHash = computeContentHash(cleanText)
                oldHash = fetchStoredHash(url)
                
                # The Magic Gatekeeper: If the hashes match, skip completely!
                if oldHash == newHash:
                    continue
                    
                # Content changed: chunk and embed
                chunks = chunkText(cleanText, pageTitle)
                chunks_data = []
                
                for chunk_idx, chunk_text in enumerate(chunks):
                    embedding = embeddingEngine.embed_query(chunk_text)
                    chunk_id = f"{url}#chunk-{chunk_idx}"
                    chunks_data.append({
                        "id": chunk_id,
                        "document": chunk_text,
                        "embedding": embedding,
                        "metadata": {
                            "source": url,
                            "title": pageTitle,
                            "chunk_index": chunk_idx
                        }
                    })
                    
                if chunks_data:
                    upsertVectorChunks(url, chunks_data)
                    updateStoredHash(url, newHash)
                    updatedPagesCount += 1
                    
            except Exception as error:
                # Live server swallows individual web crawl failures to stay online
                print(f"Failed to check delta sync for {url}: {str(error)}")
                
    print(f"Delta sync complete. [{updatedPagesCount}] pages updated.")