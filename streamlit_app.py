import streamlit as st
import streamlit.components.v1 as components
import os
import asyncio
import base64
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import core structures
from agent.graph import chatbotApp
from agent.state import ChatbotState
from utils.fileExtractor import extractTextFromFile

class StreamlitFileMock:
    def __init__(self, filename):
        self.filename = filename

# Page configuration
st.set_page_config(
    page_title="NetAssist",
    page_icon="static/favicon.png",
    layout="wide"  # Keep it wide for custom layout embedding
)

# Custom CSS to hide Streamlit headers, footers, margins and force true full-screen borderless layout
st.markdown("""
<style>
    /* Hide top header, sidebar background and footer */
    header {visibility: hidden; height: 0px !important;}
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Aggressive reset on all Streamlit page layout containers */
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    .main,
    .block-container {
        padding: 0px !important;
        margin: 0px !important;
        width: 100% !important;
        height: 100% !important;
        max-width: 100% !important;
        overflow: hidden !important;
    }
    
    /* Remove gap spacings between Streamlit elements */
    [data-testid="stVerticalBlock"],
    [data-testid="stVerticalBlock"] > div {
        padding: 0px !important;
        margin: 0px !important;
        gap: 0px !important;
    }
    
    /* Ensure component containers take full width and height */
    .element-container, .stCustomComponent {
        width: 100% !important;
        height: 100% !important;
        margin: 0px !important;
        padding: 0px !important;
    }
    
    /* Force component iframe to take up the full viewport */
    iframe {
        border: none !important;
        width: 100% !important;
        height: 100vh !important;
        display: block !important;
        margin: 0px !important;
        padding: 0px !important;
        overflow: hidden !important;
    }
</style>
""", unsafe_allow_html=True)

# Declare component pointing to the static directory
parent_dir = os.path.dirname(os.path.abspath(__file__))
build_dir = os.path.join(parent_dir, "static")
netassist_component = components.declare_component("netassist_component", path=build_dir)

# Initialize session state for tracking responses
if "lastResponse" not in st.session_state:
    st.session_state.lastResponse = ""
if "lastIntent" not in st.session_state:
    st.session_state.lastIntent = ""
if "lastTimestamp" not in st.session_state:
    st.session_state.lastTimestamp = 0
if "processedTimestamp" not in st.session_state:
    st.session_state.processedTimestamp = 0
if "chatHistory" not in st.session_state:
    st.session_state.chatHistory = []

# Call component and pass the current state
component_value = netassist_component(
    lastResponse=st.session_state.lastResponse,
    lastIntent=st.session_state.lastIntent,
    lastTimestamp=st.session_state.lastTimestamp,
    key="netassist_ui"
)

# Check if new message payload was sent from the iframe
if component_value and component_value.get("timestamp", 0) > st.session_state.processedTimestamp:
    query = component_value["query"]
    timestamp = component_value["timestamp"]
    
    # Process attached file text if present
    file_text = ""
    if "fileBase64" in component_value:
        try:
            file_bytes = base64.b64decode(component_value["fileBase64"])
            file_mock = StreamlitFileMock(component_value["fileName"])
            file_text = extractTextFromFile(file_mock, file_bytes)
        except Exception as file_err:
            st.session_state.lastResponse = f"Failed to parse uploaded file: {str(file_err)}"
            st.session_state.lastIntent = "ERROR"
            st.session_state.lastTimestamp = timestamp
            st.session_state.processedTimestamp = timestamp
            st.rerun()

    # Structure state payload
    initialState = ChatbotState(
        userQuery=query,
        chatHistory=st.session_state.chatHistory,
        fileContext=file_text,
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
        # Run the async invoker in an event loop
        finalState = asyncio.run(chatbotApp.ainvoke(initialState))
        response = finalState.get("finalResponse", "I am unable to answer that at the moment.")
        intent = finalState.get("queryIntent", "UNKNOWN")
    except Exception as e:
        response = f"Error processing query: {str(e)}"
        intent = "ERROR"
        
    # Update state
    st.session_state.lastResponse = response
    st.session_state.lastIntent = intent
    st.session_state.lastTimestamp = timestamp
    st.session_state.processedTimestamp = timestamp
    
    # Update history list
    st.session_state.chatHistory.append({"role": "user", "content": query})
    st.session_state.chatHistory.append({"role": "assistant", "content": response})
    
    # Rerun to push the new response arguments to the iframe!
    st.rerun()
