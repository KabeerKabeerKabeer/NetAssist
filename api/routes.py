import json
from fastapi import APIRouter, HTTPException, File, Form, UploadFile
from pydantic import BaseModel
from typing import Optional, List, Dict
from agent.graph import chatbotApp
from agent.state import ChatbotState
from utils.fileExtractor import extractTextFromFile

chatRouter = APIRouter()

class ChatRequest(BaseModel):
    userQuery: str
    chatHistory: Optional[List[Dict[str, str]]] = None

class ChatResponse(BaseModel):
    response: str
    intent: str
    retryCount: int

@chatRouter.post("/chat", response_model=ChatResponse)
async def processChat(requestPayload: ChatRequest):
    if not requestPayload.userQuery.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    # Initialize the LangGraph state payload
    initialState = ChatbotState(
        userQuery=requestPayload.userQuery,
        chatHistory=requestPayload.chatHistory or [],
        fileContext="",
        queryIntent="",
        extractedEntities=[],
        generatedSql="",
        sqlResult=[],
        retrievedContext=[],
        errorLog="",
        retryCount=0,
        finalResponse=""
    )
    
    try:
        # Execute the LangGraph state machine asynchronously
        finalState = await chatbotApp.ainvoke(initialState)
        
        return ChatResponse(
            response=finalState.get("finalResponse", "I am unable to answer that at the moment."),
            intent=finalState.get("queryIntent", "UNKNOWN"),
            retryCount=finalState.get("retryCount", 0)
        )
    except Exception as executionError:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(executionError)}")

@chatRouter.post("/chat/file", response_model=ChatResponse)
async def processChatWithFile(
    file: UploadFile = File(...),
    userQuery: str = Form(...),
    chatHistory: Optional[str] = Form(None)
):
    if not userQuery.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")
        
    # Parse chat history from Form parameter JSON string
    parsedHistory = []
    if chatHistory:
        try:
            parsedHistory = json.loads(chatHistory)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid chatHistory JSON format: {str(e)}")
            
    # Read file content and extract text
    try:
        content = await file.read()
        fileText = extractTextFromFile(file, content)
    except Exception as fileErr:
        if isinstance(fileErr, HTTPException):
            raise fileErr
        raise HTTPException(status_code=400, detail=f"Failed to process uploaded file: {str(fileErr)}")
        
    # Initialize state payload with fileContext
    initialState = ChatbotState(
        userQuery=userQuery,
        chatHistory=parsedHistory,
        fileContext=fileText,
        queryIntent="",
        extractedEntities=[],
        generatedSql="",
        sqlResult=[],
        retrievedContext=[],
        errorLog="",
        retryCount=0,
        finalResponse=""
    )
    
    try:
        # Execute the LangGraph state machine
        finalState = await chatbotApp.ainvoke(initialState)
        
        return ChatResponse(
            response=finalState.get("finalResponse", "I am unable to answer that at the moment."),
            intent=finalState.get("queryIntent", "UNKNOWN"),
            retryCount=finalState.get("retryCount", 0)
        )
    except Exception as executionError:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(executionError)}")