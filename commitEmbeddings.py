import os
import json
import asyncio
from core.database import updateStoredHash
from core.chromaClient import upsertVectorChunks
from core.llmClient import generateEmbeddingArray

async def commitAll():
    staging_path = "data/scraped_chunks.json"
    if not os.path.exists(staging_path):
        print(f"Staging file {staging_path} not found. Please run runManualScraper.py first!")
        return
        
    try:
        with open(staging_path, "r", encoding="utf-8") as f:
            pages = json.load(f)
    except Exception as e:
        print(f"Failed to read staging file {staging_path}: {str(e)}")
        return
        
    print("==================================================")
    print(" COMMITTING CRAWLED CHUNKS TO VECTOR DATABASE")
    print("==================================================")
    print(f"Loaded {len(pages)} scraped items from staging.\n")
    
    success_count = 0
    
    for page_idx, page in enumerate(pages):
        url = page.get("url")
        title = page.get("title") or "No Title"
        page_hash = page.get("hash")
        chunks = page.get("chunks", [])
        status = page.get("status")
        
        if status in ("failed", "http_error") or not chunks:
            print(f"[{page_idx+1}/{len(pages)}] [SKIP] Failed or empty page: {url}")
            continue
            
        print(f"[{page_idx+1}/{len(pages)}] Indexing {len(chunks)} chunks for: {url}")
        
        chunks_data = []
        failed_embedding = False
        
        for chunk_idx, chunk_text in enumerate(chunks):
            try:
                # Generate embedding utilizing retry/backoff wrappers
                embedding = await generateEmbeddingArray(chunk_text)
                
                chunk_id = f"{url}#chunk-{chunk_idx}"
                chunks_data.append({
                    "id": chunk_id,
                    "document": chunk_text,
                    "embedding": embedding,
                    "metadata": {
                        "source": url, 
                        "title": title, 
                        "chunk_index": chunk_idx
                    }
                })
            except Exception as embed_err:
                print(f"  [ERROR] Embedding failed for chunk {chunk_idx}: {str(embed_err)}")
                failed_embedding = True
                break
                
        if failed_embedding or not chunks_data:
            print(f"  [SKIP] Skipping db commit due to embedding error on {url}")
            continue
            
        try:
            # Commit to vector database
            upsertVectorChunks(url, chunks_data)
            
            # Commit hash to SQLite to recognize changes on future crawls
            updateStoredHash(url, page_hash)
            print(f"  -> Successfully committed and updated hash database.")
            success_count += 1
        except Exception as db_err:
            print(f"  [ERROR] Database commit failed for {url}: {str(db_err)}")
            
    print(f"\nIngestion process finalized. Successfully committed {success_count} pages.")

if __name__ == "__main__":
    asyncio.run(commitAll())
