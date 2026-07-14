from typing import TypedDict, List, Dict, Any

class ChatbotState(TypedDict):
    # Core Input
    userQuery: str
    chatHistory: List[Dict[str, str]]
    fileContext: str
    
    # Routing & Mapping
    queryIntent: str  # e.g., 'SQL', 'VECTOR', 'HYBRID', 'OUT_OF_DOMAIN'
    extractedEntities: List[str]  # e.g., ["Information Security", "WEOM"]
    vectorQuery: str
    
    # SQL Execution Pathway
    generatedSql: str
    sqlResult: List[Dict[str, Any]]
    
    # Vector Retrieval Pathway
    retrievedContext: List[str]
    
    # Validation & Output
    errorLog: str
    retryCount: int
    entityCorrections: List[str]
    finalResponse: str