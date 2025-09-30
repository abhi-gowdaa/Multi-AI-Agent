import asyncio
import os 
import sys
import json
from contextlib import AsyncExitStack
from typing import Optional,List
from newprompt import agent1,agent2
from voice import transcribe,record_audio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import InMemorySaver
from dotenv import load_dotenv
load_dotenv()
checkpointer = InMemorySaver()

# class CustomEncoder(json.JSONEncoder):
#     def default(self, o):
#         if hasattr(o, "content"):
#             return {"type": o.__class__.__name__, "content": o.content}
#         return super().default(o)
    
class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        data = {}

        # Always include type
        data["type"] = o.__class__.__name__

        # Content if available
        if hasattr(o, "content"):
            data["content"] = o.content

        # Tool name (for ToolMessage)
        if hasattr(o, "name") and o.name:
            data["tool_name"] = o.name

        # Tool calls (for AIMessage when it triggers a tool)
        if hasattr(o, "tool_calls") and o.tool_calls:
            data["tool_calls"] = o.tool_calls

        # Extra kwargs (like function_call details)
        if hasattr(o, "additional_kwargs") and o.additional_kwargs:
            data["additional_kwargs"] = o.additional_kwargs

        return data



llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-lite",     # Gemini model to use
    temperature=0,              # 0 = deterministic output; increase for more creativity
    max_retries=2,              # Automatically retry API calls up to 2 times for transient errors
    google_api_key=os.getenv("GOOGLE_API_KEY")  # Google API key must be set in your environment or .env file
)


if len(sys.argv) < 2:
    print("usuage python client_langchain_google_genai_bind_tools.py <path_to_server_script>")
    sys.exit(1)
server_script=sys.argv[1]


server_params= StdioServerParameters(
    command="python" if server_script.endswith(".py") else "node",
    args=[server_script]
)


# Global variable to hold the active MCP session.
# This is a simple holder with a "session" attribute for use by the tool adapter.
mcp_client=None


def get_last_message(response):
    """Simplified extraction of the last message in proper format"""
    messages = response.get('messages', [])
    if not messages:
        return None
        
    last_msg = messages[-1]
    
    # Determine role
    if 'HumanMessage' in str(type(last_msg)):
        role = 'user'
    elif 'AIMessage' in str(type(last_msg)):
        role = 'assistant'
    elif 'ToolMessage' in str(type(last_msg)):
        role = 'tool'
    else:
        role = 'assistant'
    
    # Get content
    content = getattr(last_msg, 'content', str(last_msg))
    
    return  content


async def run_agent():
    
    global mcp_client
    async with stdio_client(server_params) as (read,write):
        async with ClientSession(read,write) as session:
            await session.initialize()
            
            mcp_client = type("MCPClientHolder",(),{"session":session})
            tools=await load_mcp_tools(session)
            agent_prd=create_react_agent(llm,tools,prompt=agent1)
            agent_imp=create_react_agent(llm,tools,prompt=agent2)
            print("mcp started type quit to exit")
            
            while True:
                query = input("\nQuery (or type 'voice'): ").strip()

                if query.lower() == "voice":
                    audio_file = record_audio(duration=7)
                    query = transcribe(audio_file).strip()

                if query.lower() in ["quit", "exit", "stop"]:
                    break
                 
                
                response1 = await asyncio.wait_for(
                    agent_prd.ainvoke({"messages":query},{"recursion_limit": 50}),
                    timeout=100   # <- max seconds before stop
                )
                
                handoffresponse = get_last_message(response1)

        # asyncio.wait_for ensures a hard timeout
                response = await asyncio.wait_for(
                    agent_imp.ainvoke({"messages":handoffresponse},{"recursion_limit": 50}),
                    timeout=300   # <- max seconds before stop
                )
                 
                  
                try:
                    formatted = json.dumps(response, indent=2, cls=CustomEncoder)

                    # Add numbering to main JSON objects if it's a dict with "messages"
                    try:
                        data = json.loads(formatted)
                        if isinstance(data, dict) and "messages" in data:
                            for i, msg in enumerate(data["messages"], start=1):
                                msg["_index"] = i  # add numbering inside each message
                            formatted = json.dumps(data, indent=2, cls=CustomEncoder)
                    except Exception:
                        pass

                except Exception as e:
                    formatted = str(response)
                                
                print("\n Response:")
                print(formatted)
            return



if __name__== "__main__":
    asyncio.run(run_agent())           