import os
import random
import asyncio
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Load environment variables from the .env file
load_dotenv(override=True)

apiKey = os.getenv("GEMINI_API_KEY")
if not apiKey:
    raise ValueError("GEMINI_API_KEY is missing from the environment configuration.")

# 1. Initialize Gemini Models
# Flash-Lite handles routing, mapping, and low-complexity tasks (15 RPM)
# Fallback to standard flash to avoid quota limit issues
geminiFlashLite = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=apiKey,
    temperature=0.1
)

# Standard Flash handles SQL generation and final answer synthesis (10 RPM)
geminiFlash = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=apiKey,
    temperature=0.3
)

# Text Embedding engine for website syncing and vector searches
embeddingEngine = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=apiKey
)

# 1.5. Pricing Models and Cost Calculation
PRICING = {
    "gemini-3.1-pro": {"input": 2.00 / 1_000_000, "output": 12.00 / 1_000_000},
    "gemini-2.5-pro": {"input": 1.25 / 1_000_000, "output": 10.00 / 1_000_000},
    "gemini-3.5-flash": {"input": 1.50 / 1_000_000, "output": 9.00 / 1_000_000},
    "gemini-3.1-flash-lite": {"input": 0.25 / 1_000_000, "output": 1.50 / 1_000_000},
    "gemini-2.5-flash-lite": {"input": 0.10 / 1_000_000, "output": 0.40 / 1_000_000},
    "gemini-2.5-flash": {"input": 0.075 / 1_000_000, "output": 0.30 / 1_000_000},
    "models/gemini-embedding-001": {"input": 0.025 / 1_000_000, "output": 0.0},
}

def calculateCost(modelName: str, promptTokens: int, responseTokens: int) -> float:
    matched_key = None
    for key in PRICING:
        if key in modelName:
            matched_key = key
            break
            
    if not matched_key:
        matched_key = "gemini-2.5-flash"
        
    rates = PRICING[matched_key]
    input_rate = rates["input"]
    output_rate = rates["output"]
    
    # Context Premium rule: For Pro models (3.1 Pro and 2.5 Pro),
    # prompts exceeding 200,000 tokens are charged at double the input rate and 1.5x output rate.
    if "pro" in matched_key and promptTokens > 200_000:
        input_rate *= 2.0
        output_rate *= 1.5
        
    return (promptTokens * input_rate) + (responseTokens * output_rate)

# 2. Free Tier Resilience Wrapper (Exponential Backoff with Jitter)
async def executeWithRetry(apiFunction, *args, maxRetries=5, initialDelay=2.0, **kwargs):
    """
    Executes a Gemini API call asynchronously. If a rate limit (429) 
    or transient error occurs, it backs off exponentially with random jitter.
    """
    currentDelay = initialDelay
    
    for attempt in range(maxRetries):
        try:
            # Check if the passed function is a coroutine or standard callable
            if asyncio.iscoroutinefunction(apiFunction):
                return await apiFunction(*args, **kwargs)
            else:
                return apiFunction(*args, **kwargs)
                
        except Exception as executionError:
            # Detect rate limits or quota errors from the status code or error message
            errorMessage = str(executionError).lower()
            isRateLimit = "429" in errorMessage or "quota" in errorMessage or "resource_exhausted" in errorMessage
            
            if isRateLimit and attempt < maxRetries - 1:
                # Add random jitter to break simultaneous request cycles
                jitter = random.uniform(0.5, 1.5)
                sleepDuration = currentDelay * jitter
                
                print(f"[Rate Limit Detected] Attempt {attempt + 1} failed. Backing off for {sleepDuration:.2f} seconds...")
                await asyncio.sleep(sleepDuration)
                
                # Double the base delay for the next fallback iteration
                currentDelay *= 2.0
            else:
                # Re-raise the exception if retries are exhausted or it's a structural error (e.g., bad syntax)
                print(f"API execution permanently failed on attempt {attempt + 1}: {executionError}")
                raise executionError

# --- High-Level Executables Used Across the Project ---

async def generateEmbeddingArray(textContent):
    """
    Wraps the embedding call inside the resilience layer.
    Used by scraper/syncTask.py to convert raw text into vectors.
    """
    async def embeddingTask():
        return embeddingEngine.embed_query(textContent)
        
    embedding = await executeWithRetry(embeddingTask)
    
    try:
        modelName = "models/gemini-embedding-001"
        # GoogleGenerativeAIEmbeddings has no get_num_tokens, use geminiFlashLite to count prompt tokens
        promptTokens = geminiFlashLite.get_num_tokens(textContent)
        responseTokens = 0
        estimatedCost = calculateCost(modelName, promptTokens, responseTokens)
        
        from core.database import logLLMUsage
        logLLMUsage(modelName, promptTokens, responseTokens, estimatedCost)
    except Exception as logErr:
        print(f"[LLM Usage Logger Error] Failed to log embedding usage: {logErr}")
        
    return embedding

async def invokeFlashLite(promptPayload):
    """
    Asynchronously invokes the high-speed Flash-Lite model with retry safety.
    """
    async def flashLiteTask():
        return await geminiFlashLite.ainvoke(promptPayload)
        
    response = await executeWithRetry(flashLiteTask)
    
    try:
        modelName = "gemini-2.5-flash"
        promptStr = str(promptPayload)
        promptTokens = geminiFlashLite.get_num_tokens(promptStr)
        responseTokens = geminiFlashLite.get_num_tokens(response.content)
        estimatedCost = calculateCost(modelName, promptTokens, responseTokens)
        
        from core.database import logLLMUsage
        logLLMUsage(modelName, promptTokens, responseTokens, estimatedCost)
    except Exception as logErr:
        print(f"[LLM Usage Logger Error] Failed to log Flash-Lite usage: {logErr}")
        
    return response.content

async def invokeFlash(promptPayload):
    """
    Asynchronously invokes the high-reasoning Flash model with retry safety.
    """
    async def flashTask():
        return await geminiFlash.ainvoke(promptPayload)
        
    response = await executeWithRetry(flashTask)
    
    try:
        modelName = "gemini-2.5-flash"
        promptStr = str(promptPayload)
        promptTokens = geminiFlash.get_num_tokens(promptStr)
        responseTokens = geminiFlash.get_num_tokens(response.content)
        estimatedCost = calculateCost(modelName, promptTokens, responseTokens)
        
        from core.database import logLLMUsage
        logLLMUsage(modelName, promptTokens, responseTokens, estimatedCost)
    except Exception as logErr:
        print(f"[LLM Usage Logger Error] Failed to log Flash usage: {logErr}")
        
    return response.content