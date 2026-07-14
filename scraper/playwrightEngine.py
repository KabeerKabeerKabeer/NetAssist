import time
from playwright.sync_api import sync_playwright

class PlaywrightBrowser:
    def __init__(self, headless=True, timeout_ms=25000):
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()
        # Launch Chromium headless with robust arguments
        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-gpu", "--no-sandbox"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout_ms)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
        finally:
            if self.playwright:
                self.playwright.stop()

    def fetch_page(self, url):
        """
        Navigates to the url, waits for network requests to settle,
        scrolls down the page to trigger lazy loading of cards, and
        returns (html_content, page_title, status_code).
        """
        try:
            # Go to page and wait for document load
            response = self.page.goto(url, wait_until="load")
            status_code = response.status if response else 200
            
            # Wait for network idle (up to 5s) to allow async calls/cards to populate
            try:
                self.page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass # Networkidle can time out if page has persistent tracker pixels, which is safe to ignore
                
            # Scroll down incrementally to trigger lazy loading (e.g. team profile cards)
            try:
                # Scroll in increments of 800px up to 10 times (~8000px height pages)
                for _ in range(10):
                    self.page.evaluate("window.scrollBy(0, 800)")
                    self.page.wait_for_timeout(350)
                
                # Scroll back to top to ensure complete DOM state layout is finalized
                self.page.evaluate("window.scrollTo(0, 0)")
                self.page.wait_for_timeout(400)
            except Exception as scroll_err:
                print(f"  [WARNING] Scroll execution failed on {url}: {scroll_err}")
                
            html_content = self.page.content()
            page_title = self.page.title().strip() if self.page.title() else "No Title"
            
            return html_content, page_title, status_code
        except Exception as e:
            raise RuntimeError(f"Playwright navigation failed: {str(e)}")
