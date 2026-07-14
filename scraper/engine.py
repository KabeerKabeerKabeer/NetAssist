import httpx
from bs4 import BeautifulSoup
import hashlib
from urllib.parse import urljoin, urlparse
import asyncio

class WebScraper:
    def __init__(self, baseUrl, maxPages=50):
        self.baseUrl = baseUrl
        self.maxPages = maxPages
        self.visitedUrls = set()
        
    def generateHash(self, textContent):
        # Create a unique fingerprint using MD5
        return hashlib.md5(textContent.encode('utf-8')).hexdigest()

    def isValidUrl(self, url):
        # Ensure we don't crawl external sites, PDFs, or irrelevant archives
        parsedUrl = urlparse(url)
        parsedBase = urlparse(self.baseUrl)
        
        if parsedUrl.netloc != parsedBase.netloc:
            return False
            
        skipExtensions = ('.pdf', '.jpg', '.png', '.mp4')
        if url.endswith(skipExtensions):
            return False
            
        return True

    def extractCleanText(self, htmlContent):
        soup = BeautifulSoup(htmlContent, 'html.parser')
        
        # Remove noisy elements
        for scriptOrStyle in soup(['script', 'style', 'header', 'footer', 'nav']):
            scriptOrStyle.decompose()
            
        rawText = soup.get_text(separator=' ', strip=True)
        # Clean up multi-spaces
        cleanText = ' '.join(rawText.split())
        return cleanText

    async def fetchPage(self, url, httpClient):
        try:
            response = await httpClient.get(url, timeout=10.0)
            response.raise_for_status()
            return response.text
        except Exception as errorMsg:
            print(f"Failed to fetch {url}: {errorMsg}")
            return None

    async def crawl(self):
        urlsToVisit = [self.baseUrl]
        scrapedData = []

        async with httpx.AsyncClient() as httpClient:
            while urlsToVisit and len(self.visitedUrls) < self.maxPages:
                currentUrl = urlsToVisit.pop(0)
                
                if currentUrl in self.visitedUrls:
                    continue
                    
                self.visitedUrls.add(currentUrl)
                pageHtml = await self.fetchPage(currentUrl, httpClient)
                
                if not pageHtml:
                    continue

                cleanText = self.extractCleanText(pageHtml)
                if len(cleanText) > 200: # Ignore pages with almost no text
                    contentHash = self.generateHash(cleanText)
                    scrapedData.append({
                        "url": currentUrl,
                        "text": cleanText,
                        "hash": contentHash
                    })

                # Find new links to crawl
                soup = BeautifulSoup(pageHtml, 'html.parser')
                for anchor in soup.find_all('a', href=True):
                    nextUrl = urljoin(currentUrl, anchor['href'])
                    # Strip fragments (#) to avoid duplicating same page
                    nextUrl = nextUrl.split('#')[0] 
                    
                    if self.isValidUrl(nextUrl) and nextUrl not in self.visitedUrls:
                        urlsToVisit.append(nextUrl)
                        
                # Be polite to the server
                await asyncio.sleep(0.5)

        return scrapedData