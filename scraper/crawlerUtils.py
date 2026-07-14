from urllib.parse import urlparse

def shouldProcessUrl(url):
    """
    Validates if a URL belongs to the allowed domains, is not a static asset,
    and is not a news, blog, or press release page.
    """
    if not url:
        return False
        
    try:
        parsed = urlparse(url)
        
        # 1. Domain boundaries
        allowed_domains = ["netsoltech.com", "ir.netsoltech.com"]
        domain_matched = False
        netloc = parsed.netloc.lower()
        
        for domain in allowed_domains:
            if netloc == domain or netloc.endswith("." + domain):
                domain_matched = True
                break
                
        if not domain_matched:
            return False
            
        # 2. Exclude static/asset file extensions
        skip_extensions = (
            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.mp4', 
            '.zip', '.gz', '.tar', '.xlsx', '.csv', '.doc', '.docx'
        )
        path = parsed.path.lower()
        if path.endswith(skip_extensions):
            return False
            
        # 3. Exclude news, blogs, insights sub-articles, etc.
        # Skip landing pages or articles containing these path segments
        skip_paths = [
            "/blog", 
            "/news", 
            "/press-release", 
            "/pressrelease", 
            "/event", 
            "/testimonial", 
            "/podcast", 
            "/whitepaper", 
            "/case-study", 
            "/casestudy",
            "/insights/" # skips individual articles under insights, keeps '/insights'
        ]
        
        for skip_path in skip_paths:
            if skip_path in path:
                return False
                
        # Skip query parameters related to news/press
        query = parsed.query.lower()
        if "news" in query or "press" in query:
            return False
            
        return True
    except Exception:
        return False

def chunkText(text, pageTitle, chunkSize=1000, overlap=100):
    """
    Splits text content into overlapping chunks of chunkSize characters.
    Attempts to break on sentence/word boundaries (whitespace or punctuation)
    to maintain semantic meaning. Prepend page title metadata to each chunk.
    """
    if not text:
        return []
        
    chunks = []
    # Clean redundant spaces
    cleaned_text = " ".join(text.split())
    
    if len(cleaned_text) <= chunkSize:
        return [f"Title: {pageTitle}\nContent: {cleaned_text}"]
        
    start = 0
    text_len = len(cleaned_text)
    
    while start < text_len:
        end = start + chunkSize
        if end >= text_len:
            chunk_content = cleaned_text[start:]
            chunks.append(f"Title: {pageTitle}\nContent: {chunk_content}")
            break
            
        # Look back up to 50 characters to find a word or sentence boundary
        split_pos = end
        for i in range(50):
            char_pos = end - i
            if char_pos <= start:
                break
            if cleaned_text[char_pos] in (' ', '\n', '.', '!', '?'):
                split_pos = char_pos + 1
                break
                
        chunk_content = cleaned_text[start:split_pos].strip()
        chunks.append(f"Title: {pageTitle}\nContent: {chunk_content}")
        
        # Advance by the size minus overlap
        start = split_pos - overlap
        if start >= text_len or split_pos <= start:
            # Prevent infinite loop in edge cases where we can't advance
            start = split_pos
            
    return chunks
