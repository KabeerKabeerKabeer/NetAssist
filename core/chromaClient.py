import chromadb
import os

# 1. Initialize the Persistent Storage Location
# Using absolute paths prevents errors depending on where you run the FastAPI script from.
storagePath = os.path.abspath("data/chromaStorage")

# Initialize the persistent client
# If the folder doesn't exist, ChromaDB will automatically create it.
vectorDbClient = chromadb.PersistentClient(path=storagePath)

# 2. Define the Collection
collectionName = "netsolWebsite"

# We configure 'cosine' similarity, which is the industry standard for 
# measuring the semantic distance between LLM text embeddings.
webCollection = vectorDbClient.get_or_create_collection(
    name=collectionName,
    metadata={"hnsw:space": "cosine"} 
)

# --- Write Operations (Used by scraper/syncTask.py) ---

def upsertVectorDocument(pageUrl, textContent, embeddingArray, metadataPayload):
    """
    Inserts or updates a document in the vector database.
    If the pageUrl (ID) already exists, it overwrites it seamlessly.
    """
    webCollection.upsert(
        ids=[pageUrl],
        embeddings=[embeddingArray],
        documents=[textContent],
        metadatas=[metadataPayload]
    )
    print(f"Successfully upserted vector for {pageUrl}")

def deleteVectorDocument(pageUrl):
    """
    Removes a document and all its chunks from the vector database.
    Used if a page is deleted from the live Netsol website.
    """
    try:
        webCollection.delete(where={"source": pageUrl})
        print(f"Successfully deleted vector chunks for {pageUrl}")
    except Exception as e:
        print(f"Failed to delete vector chunks for {pageUrl}: {str(e)}")

def upsertVectorChunks(pageUrl, chunksData):
    """
    Inserts or updates multiple chunks of a document in the vector database.
    Automatically deletes previous chunks for pageUrl to avoid orphans.
    """
    try:
        webCollection.delete(where={"source": pageUrl})
    except Exception as e:
        print(f"No existing chunks found to delete for {pageUrl} or delete failed: {str(e)}")
        
    if not chunksData:
        print(f"No new chunks to insert for {pageUrl}")
        return
        
    ids = [c["id"] for c in chunksData]
    embeddings = [c["embedding"] for c in chunksData]
    documents = [c["document"] for c in chunksData]
    metadatas = [c["metadata"] for c in chunksData]
    
    webCollection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas
    )
    print(f"Successfully upserted {len(chunksData)} vector chunks for {pageUrl}")

# --- Read Operations (Used by agent/nodes.py) ---

def queryVectorDatabase(queryVector, topK=4):
    """
    Searches the vector database for the most semantically similar chunks.
    Returns the raw text documents and their source URLs.
    """
    searchResults = webCollection.query(
        query_embeddings=[queryVector],
        n_results=topK
    )
    
    # Chroma returns lists of lists, we flatten this for the LangGraph context
    extractedContext = []
    
    if searchResults.get('documents') and searchResults['documents'][0]:
        documents = searchResults['documents'][0]
        # Safely handle potential None or empty metadatas from Chroma
        metadatas = searchResults.get('metadatas', [[]])[0] if searchResults.get('metadatas') else []
        
        for index in range(len(documents)):
            sourceUrl = "Unknown Source"
            if metadatas and index < len(metadatas) and metadatas[index]:
                sourceUrl = metadatas[index].get("source", "Unknown Source")
            text = documents[index]
            extractedContext.append(f"[Source: {sourceUrl}]\n{text}")
            
    return extractedContext

# Alias for backwards compatibility if needed
retrieveSimilarDocuments = queryVectorDatabase