import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.database import setupDatabase, ingestEmployeeData, getReadOnlyConnection
from scraper.syncTask import executeDeltaSync
from fastapi.staticfiles import StaticFiles
from api.routes import chatRouter

@asynccontextmanager
async def appLifespan(fastapiApp: FastAPI):
    # --- Boot Sequence ---
    print("Initializing SQLite Database...")
    setupDatabase()
    
    # Check if the database needs initial population
    dbConnection = getReadOnlyConnection()
    dbCursor = dbConnection.cursor()
    dbCursor.execute("SELECT COUNT(*) FROM EmployeeProfiles")
    profileCount = dbCursor.fetchone()[0]
    dbConnection.close()
    
    if profileCount == 0 and os.path.exists(settings.employeeJsonPath):
        print("Empty database detected. Ingesting core JSON data...")
        ingestEmployeeData(settings.employeeJsonPath)
    
    print("Generating Pipeline Graph Architecture...")
    try:
        import generate_graph_data
    except Exception as e:
        print(f"Warning: Pipeline graph auto-generation failed: {e}")

    print("Starting Background Task Scheduler...")
    taskScheduler = AsyncIOScheduler()
    
    # Schedule the delta scraper
    taskScheduler.add_job(
        executeDeltaSync, 
        'interval', 
        hours=settings.syncIntervalHours
    )
    taskScheduler.start()
    
    # Fire an immediate non-blocking sync on server startup
    asyncio.create_task(asyncio.to_thread(executeDeltaSync))
    
    print("Netsol Hybrid Intelligence API is live and listening.")
    
    yield  # Server handles HTTP requests here
    
    # --- Teardown Sequence ---
    print("Shutting down background tasks safely...")
    taskScheduler.shutdown(wait=True)

# Initialize the Application
chatbotApi = FastAPI(
    title="Netsol Hybrid Intelligence",
    description="Agentic Text-to-SQL and Vector RAG Architecture",
    version="1.0.0",
    lifespan=appLifespan
)

# Register the routes
chatbotApi.include_router(chatRouter, prefix="/api/v1")

# Serve the static frontend files
chatbotApi.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Execute the server
    uvicorn.run("main:chatbotApi", host="127.0.0.1", port=8000, reload=True)