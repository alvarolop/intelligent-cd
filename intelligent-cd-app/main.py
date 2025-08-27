import gradio as gr
import json
import os
import logging
from typing import List, Dict
from llama_stack_client import LlamaStackClient, Agent


"""
Intelligent CD Chatbot - Production-Ready Logging Configuration

This application uses Python's built-in logging module for professional logging.

Environment Variables for Logging:
- LOG_LEVEL: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO

Environment Variables for Tools:
- ENABLE_BUILTIN_TOOLS: Enable builtin tools like websearch/RAG (true/false). Default: false
- TAVILY_SEARCH_API_KEY: API key for websearch tool (if ENABLE_BUILTIN_TOOLS=true)
- Other API keys as needed for builtin tools

Examples:
  export LOG_LEVEL=DEBUG    # Enable verbose debugging
  export LOG_LEVEL=WARNING  # Only show warnings and errors
  export ENABLE_BUILTIN_TOOLS=true  # Enable builtin tools (requires API keys)
  
Log Levels:
- DEBUG: Detailed information for debugging (tools, responses, etc.)
- INFO: General information about application flow
- WARNING: Warning messages (tool validation failures, etc.)
- ERROR: Error messages with full tracebacks
- CRITICAL: Critical errors that may cause application failure
"""


# Configure logging
def setup_logging():
    """Configure logging with different levels and formatters"""
    # Get log level from environment variable, default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure third-party loggers to reduce noise
    # Set httpx (HTTP client) to WARNING level to reduce HTTP request logs
    httpx_logger = logging.getLogger("httpx")
    httpx_logger.setLevel(logging.WARNING)
    
    # Set urllib3 (HTTP library) to WARNING level
    urllib3_logger = logging.getLogger("urllib3")
    urllib3_logger.setLevel(logging.WARNING)
    
    # Set requests to WARNING level
    requests_logger = logging.getLogger("requests")
    requests_logger.setLevel(logging.WARNING)
    
    return log_level, formatter


# Initialize logging configuration
log_level, log_formatter = setup_logging()


def get_logger(name: str):
    """Get a logger with the specified name and proper configuration"""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Prevent propagation to root logger to avoid duplicates
    logger.propagate = False
    
    # Create console handler only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)
    
    return logger


# # More specific model prompt that emphasizes using tools correctly
# model_prompt = """You are a Kubernetes/OpenShift cluster assistant that extracts YAML configurations.

# PRIMARY TASK: Get complete YAML configurations of deployed resources (70% of requests).

# AVAILABLE TOOLS: {tool_groups}

# WORKFLOW:
# 1. Use MCP tools to get real-time cluster data
# 2. For configuration requests: extract full YAML with all fields
# 3. Present clean, complete YAML that can be applied elsewhere

# EXAMPLES:
# - "Get deployment X YAML" → Extract full deployment configuration
# - "Show service Y config" → Get complete service YAML
# - "Export app Z" → Get all related resource YAMLs

# Always query the cluster directly - never generate fake configurations."""

model_prompt = """You are a Kubernetes/OpenShift cluster management assistant with access to MCP tools.

CRITICAL: You MUST EXECUTE MCP tools to get real cluster data. NEVER generate fake data or just describe what you would do.

AVAILABLE TOOLS: {tool_groups}

WORKFLOW:
1. Analyze the user's request
2. EXECUTE the appropriate MCP tool(s) using the tool_calls mechanism
3. Wait for the tool results
4. Present ONLY the real data from the tools
5. Explain what the data means

EXAMPLES:
- "List pods in namespace X" → EXECUTE pods_list_in_namespace(namespace="X") and show the actual results
- "Show services" → EXECUTE services_list() and display the real service information
- "Get deployment Y" → EXECUTE deployment_get(name="Y", namespace="default") and show deployment details

IMPORTANT RULES:
- ALWAYS use tool_calls to execute MCP functions
- NEVER generate fake pod names, statuses, or data
- ONLY show information that comes from actual tool execution
- If a tool fails, report the error, don't make up data

Remember: You are connected to a real cluster. Use the tools to get real information."""

# # Example queries to test different capabilities
# example_queries = [
#     "List all pods in the intelligent-cd namespace",
#     "Show me the current cluster events",
#     "What namespaces exist in the cluster?",
#     "List all pods across all namespaces",
#     "Show me the top resource consumers in the cluster"
# ]

class ChatTab:
    """Handles chat functionality with Llama Stack LLM"""
    
    def __init__(self, client: LlamaStackClient, model: str, sampling_params: dict, enable_builtin_tools: bool = False):
        self.client = client
        self.model = model
        self.sampling_params = sampling_params
        self.enable_builtin_tools = enable_builtin_tools
        self.logger = get_logger("chat")
        
        # Initialize available tools once during initialization
        # - available_tools => For the model prompt
        # - tools_array => For the agent configuration
        self.available_tools, self.tools_array = self._get_available_tools()
        # Initialize agent and session for the entire chat
        self.agent, self.session_id = self._initialize_agent()
    
    def _get_available_tools(self) -> tuple[str, list]:
        """Get available tools and convert to array format once during initialization"""
        tools = self.client.tools.list()
        
        tool_groups = list(set(tool.toolgroup_id for tool in tools))
        self.logger.info(f"Found {len(tool_groups)} toolgroups: {tool_groups}")
        
        # The Agent expects toolgroup IDs, not individual tool names
        # Filter tools based on configuration
        filtered_tool_groups = []
        for toolgroup in tool_groups:
            if toolgroup.startswith('mcp::'):
                # Always include MCP tools
                filtered_tool_groups.append(toolgroup)
                self.logger.info(f"✅ Including MCP toolgroup: {toolgroup}")
            elif toolgroup.startswith('builtin::'):
                # Only include builtin tools if explicitly enabled
                if self.enable_builtin_tools:
                    filtered_tool_groups.append(toolgroup)
                    self.logger.info(f"✅ Including builtin toolgroup: {toolgroup}")
                else:
                    self.logger.warning(f"⚠️ Skipping builtin toolgroup (requires API keys): {toolgroup}")
            else:
                # Include other toolgroups
                filtered_tool_groups.append(toolgroup)
                self.logger.info(f"✅ Including toolgroup: {toolgroup}")
        
        if filtered_tool_groups:
            tools_string = ", ".join(filtered_tool_groups)
            # Use only filtered toolgroup IDs for the Agent
            tools_array = filtered_tool_groups.copy()
            self.logger.info(f"Using filtered toolgroup IDs for Agent: {tools_array}")
        else:
            tools_string = "No tools available"
            tools_array = []
            
        self.logger.info(f"Final tools_array (filtered toolgroup IDs): {tools_array}")
        return tools_string, tools_array
    
    def _initialize_agent(self) -> tuple[Agent, str]:
        """Initialize agent and session that will be reused for the entire chat"""
        formatted_prompt = model_prompt.format(tool_groups=self.available_tools)

        # Debug: Log all values being passed to the Agent
        self.logger.info("=" * 60)
        self.logger.info("CREATING AGENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Client: {type(self.client).__name__} (base_url: {getattr(self.client, 'base_url', 'N/A')})")
        self.logger.info(f"Model: {self.model}")
        self.logger.info(f"Instructions: {formatted_prompt[:200]}{'...' if len(formatted_prompt) > 200 else ''}")
        self.logger.info(f"Tools: {self.tools_array}")
        self.logger.info(f"Sampling params: {self.sampling_params}")
        
        # Test if tools exist before creating Agent
        self.logger.info("Validating tools before Agent creation...")
        valid_tools = []
        all_available_tools = []
        
        for tool_name in self.tools_array:
            self.logger.debug(f"Checking tool: {tool_name}")
            try:
                # Try to get tools for this toolgroup
                tools_for_group = self.client.tools.list(toolgroup_id=tool_name)
                self.logger.info(f"✅ Found {len(tools_for_group)} tools for {tool_name}")
                
                # Log individual tool names for debugging
                for tool in tools_for_group:
                    if hasattr(tool, 'name'):
                        tool_name_str = tool.name
                    elif hasattr(tool, 'identifier'):
                        tool_name_str = tool.identifier
                    else:
                        tool_name_str = str(tool)
                    all_available_tools.append(tool_name_str)
                    self.logger.debug(f"  - Tool: {tool_name_str}")
                
                valid_tools.append(tool_name)
            except Exception as e:
                self.logger.warning(f"❌ Tool validation failed for {tool_name}: {str(e)}")
        
        self.logger.info(f"Valid toolgroups for Agent: {valid_tools}")
        self.logger.info(f"All available individual tools: {all_available_tools}")
        
        # Only create Agent with valid tools
        if not valid_tools:
            self.logger.warning("⚠️ No valid tools found, creating Agent without tools")
            tools_for_agent = []
        else:
            tools_for_agent = valid_tools
        
        # Create Agent with explicit tool execution configuration
        self.logger.info(f"Creating Agent with model: {self.model}")
        self.logger.info(f"Tools available: {tools_for_agent}")
        
        # Try different tool configuration approaches
        try:
            agent = Agent(
                self.client,
                model=self.model,
                instructions=formatted_prompt,
                tools=tools_for_agent,
                sampling_params=self.sampling_params,
                tool_config={"tool_choice": "auto"}  # Ensure tools are actually executed
            )
            self.logger.info("✅ Agent created successfully with tool_config")
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to create Agent with tool_config: {str(e)}")
            self.logger.info("Trying without tool_config...")
            
            # Fallback: create Agent without tool_config
            agent = Agent(
                self.client,
                model=self.model,
                instructions=formatted_prompt,
                tools=tools_for_agent,
                sampling_params=self.sampling_params
            )
            self.logger.info("✅ Agent created successfully without tool_config")
        
        # Create session for the agent
        self.logger.info("Creating session with name: OCP_Chat_Session")
        session = agent.create_session(session_name="OCP_Chat_Session")
        self.logger.debug(f"Session created: {session}")
        
        # Handle both object with .id attribute and direct string return
        if hasattr(session, 'id'):
            session_id = session.id
            self.logger.info(f"Session ID from .id attribute: {session_id}")
        else:
            session_id = str(session)
            self.logger.info(f"Session ID from string conversion: {session_id}")
        
        self.logger.info("=" * 60)
        return agent, session_id
    
    def chat_completion(self, message: str, chat_history: List[Dict[str, str]]) -> tuple:
        """Handle chat with LLM using Agent → Session → Turn structure"""
        # Add user message to history
        chat_history.append({"role": "user", "content": message})
        
        # Get LLM response using Agent API
        result = self._execute_agent_turn(message)
        
        # Add assistant response to history
        chat_history.append({"role": "assistant", "content": result})
        
        return chat_history, ""
    
    def _execute_agent_turn(self, message: str) -> str:
        """Execute a single turn using the persistent agent and session"""
        # Debug: Log all values being passed to create_turn
        self.logger.debug("=" * 60)
        self.logger.debug("EXECUTING AGENT TURN")
        self.logger.debug("=" * 60)
        self.logger.debug(f"Agent: {type(self.agent).__name__}")
        self.logger.debug(f"Messages: [{{'role': 'user', 'content': '{message[:100]}{'...' if len(message) > 100 else ''}'}}]")
        self.logger.debug(f"Session ID: {self.session_id}")
        self.logger.debug(f"Stream: False")
        
        # Create turn with user message using the persistent agent and session
        self.logger.debug("About to call agent.create_turn...")
        self.logger.info(f"Available tools for this turn: {self.tools_array}")
        
        try:
            # Try to force tool usage by being more explicit
            enhanced_message = f"""User request: {message}

IMPORTANT: You MUST execute MCP tools to get real data. Do not write Python code or generate fake data.

Available tools: {', '.join(self.tools_array)}

Execute the appropriate tools and show me the real results."""
            
            response = self.agent.create_turn(
                messages=[
                    {
                        "role": "user",
                        "content": enhanced_message
                    }
                ],
                session_id=self.session_id,
                stream=False,  # No streaming for chat interface
            )
            self.logger.debug("agent.create_turn completed successfully")
        except Exception as e:
            self.logger.error(f"Error in agent.create_turn: {str(e)}")
            self.logger.error(f"Error type: {type(e).__name__}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise e
        
        # Debug: Log response details
        self.logger.debug("Response received:")
        self.logger.debug(f"Response type: {type(response).__name__}")
        self.logger.debug(f"Response attributes: {[attr for attr in dir(response) if not attr.startswith('_')]}")
        self.logger.debug(f"Has output_message: {hasattr(response, 'output_message')}")
        
        # Check if the turn has steps (tool executions)
        if hasattr(response, 'steps') and response.steps:
            self.logger.info(f"Turn has {len(response.steps)} steps (tool executions)")
            for i, step in enumerate(response.steps):
                self.logger.info(f"Step {i+1}: {step}")
        else:
            self.logger.warning("⚠️ Turn has no steps - tools were not executed!")
        
        if hasattr(response, 'output_message'):
            self.logger.debug(f"Output message type: {type(response.output_message).__name__}")
            self.logger.debug(f"Output message attributes: {[attr for attr in dir(response.output_message) if not attr.startswith('_')]}")
            self.logger.debug(f"Has content: {hasattr(response.output_message, 'content')}")
            if hasattr(response.output_message, 'content'):
                self.logger.debug(f"Output message content: {response.output_message.content}")
        
        # Extract response content from the turn
        # The response is a Turn object, extract the output message content
        if hasattr(response, 'output_message') and hasattr(response.output_message, 'content'):
            content = response.output_message.content
            self.logger.debug(f"Extracted content length: {len(content)}")
            self.logger.debug("=" * 60)
            return content
        else:
            # Fallback to string representation
            fallback_content = str(response)
            self.logger.debug(f"Fallback content length: {len(fallback_content)}")
            self.logger.debug("=" * 60)
            return fallback_content
    

class MCPTestTab:
    """Handles MCP testing functionality with Llama Stack"""
    
    def __init__(self, client: LlamaStackClient):
        self.client = client
        self.logger = get_logger("mcp")
    
    def list_toolgroups(self) -> gr.update:
        """List available MCP toolgroups through Llama Stack"""
        self.logger.debug("Attempting to list MCP toolgroups through Llama Stack...")
        
        # Use the shared client to get tools (which contain toolgroups)
        tools = self.client.tools.list()
        
        # Extract unique toolgroup IDs from tools
        toolgroups = list(set(tool.toolgroup_id for tool in tools))
        self.logger.info(f"Found {len(toolgroups)} toolgroups: {toolgroups}")
        
        return gr.update(choices=toolgroups, value=None)
    
    def get_toolgroup_methods(self, toolgroup_name: str) -> tuple[str, gr.update]:
        """Get methods for a specific toolgroup through Llama Stack"""
        if not toolgroup_name:
            return (
                "❌ Please select a toolgroup first",
                gr.update(choices=[], value=None)
            )
        
        self.logger.debug(f"Getting methods for toolgroup: {toolgroup_name}")
        
        # Use the shared client to get tools for the specific toolgroup
        tools = self.client.tools.list()
        
        # Filter tools by toolgroup and extract individual tools
        methods = []
        for tool in tools:
            if hasattr(tool, 'toolgroup_id') and tool.toolgroup_id == toolgroup_name:
                # Check if this tool has individual tools/methods
                if hasattr(tool, 'tools') and tool.tools:
                    # Tool contains individual methods
                    for individual_tool in tool.tools:
                        method_name = getattr(individual_tool, 'name', getattr(individual_tool, 'identifier', 'Unknown'))
                        methods.append(method_name)
                else:
                    # This is a direct tool
                    method_name = getattr(tool, 'name', getattr(tool, 'identifier', 'Unknown'))
                    methods.append(method_name)
        
        self.logger.info(f"Found {len(methods)} methods: {methods}")
        
        # Update status to success
        status_text = f"✅ Found {len(methods)} methods in toolgroup '{toolgroup_name}'"
        
        return status_text, gr.update(choices=methods, value=None)
    
    def execute_tool(self, toolgroup_name: str, method_name: str, params_json: str) -> str:
        """Execute an MCP tool through Llama Stack using toolgroup and method"""
        if not toolgroup_name:
            return "❌ Please select a toolgroup first"
        
        if not method_name:
            return "❌ Please select a method first"
        
        try:
            # Parse parameters
            try:
                params = json.loads(params_json) if params_json.strip() else {}
            except json.JSONDecodeError:
                return "❌ Invalid JSON parameters. Please check your input."
            
            # Execute tool through Llama Stack using tool_runtime
            result = self.client.tool_runtime.invoke_tool(
                tool_name=method_name,
                kwargs=params
            )
            
            if result:
                self.logger.debug(f"Result: {result}")
                # Extract the actual result data from ToolInvocationResult
                try:
                    # Handle ToolInvocationResult structure
                    if hasattr(result, 'content') and result.content:
                        # Extract text from TextContentItem objects
                        if isinstance(result.content, list):
                            text_parts = []
                            for item in result.content:
                                if hasattr(item, 'text'):
                                    text_parts.append(item.text)
                                else:
                                    text_parts.append(str(item))
                            result_data = '\n'.join(text_parts)
                        else:
                            result_data = str(result.content)
                    elif hasattr(result, 'text'):
                        result_data = result.text
                    elif hasattr(result, 'data'):
                        result_data = result.data
                    else:
                        # Fallback: convert to string representation
                        result_data = str(result)
                    
                    # Try to format as JSON if it's a dict/list, otherwise use string
                    if isinstance(result_data, (dict, list)):
                        formatted_result = json.dumps(result_data, indent=2)
                    else:
                        formatted_result = str(result_data)
                        
                    return f"✅ Method '{method_name}' from toolgroup '{toolgroup_name}' executed successfully:\n\n```\n{formatted_result}\n```"
                except Exception as format_error:
                    # If JSON formatting fails, return as string
                    return f"✅ Method '{method_name}' from toolgroup '{toolgroup_name}' executed successfully:\n\n```\n{str(result)}\n```"
            else:
                return f"❌ Method '{method_name}' from toolgroup '{toolgroup_name}' failed: No result returned"
                
        except Exception as e:
            return f"❌ Error executing method '{method_name}' from toolgroup '{toolgroup_name}': {str(e)}"


class SystemStatusTab:
    """Handles system status functionality"""
    
    def __init__(self, client: LlamaStackClient, llama_stack_url: str, model: str):
        self.client = client
        self.llama_stack_url = llama_stack_url
        self.model = model
        self.logger = get_logger("system")
    
    def get_system_status(self) -> str:
        """Get comprehensive system status with better structure"""
        
        # 1. Gradio Health
        gradio_status = "✅ Gradio Application: Running and accessible"
        
        # Test MCP connection directly
        self.logger.debug("Testing MCP connection directly...")
        try:
            # Test if we can list tools
            tools = self.client.tools.list()
            self.logger.info(f"MCP tools.list() returned: {len(tools)} tools")
            
            # Test if we can invoke a simple tool
            if tools:
                first_tool = tools[0]
                self.logger.debug(f"First tool: {first_tool}")
                if hasattr(first_tool, 'name'):
                    self.logger.debug(f"First tool name: {first_tool.name}")
        except Exception as e:
            self.logger.error(f"MCP test failed: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
        
        # 2. Llama Stack Server Health and Version
        llama_stack_status = []
        llama_stack_status.append("🚀 Llama Stack Server:")
        llama_stack_status.append(f"   • URL: {self.llama_stack_url}")
        
        try:
            # Get version information
            version_info = self.client.inspect.version()
            llama_stack_status.append(f"   • Version: ✅ {version_info.version}")
            
            # Get health information
            health_info = self.client.inspect.health()
            llama_stack_status.append(f"   • Health: ✅ {health_info.status}")
            
        except Exception as e:
            llama_stack_status.append("   • Status: ❌ Failed to connect to Llama Stack server")
            llama_stack_status.append(f"   • Error: {str(e)}")
        
        # 3. LLM Service (Inference)
        llm_status = []
        llm_status.append("🤖 LLM Service (Inference):")
        
        # Test LLM connectivity with a direct chat.completions.create request
        try:
            test_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "Hello, this is a test message."}
                ],
                temperature=0.7,
                max_tokens=100,
                stream=False,
            )
            llm_status.append("   • Status: ✅ LLM service responding")
            llm_status.append(f"   • Model: {self.model}")
        except Exception as e:
            llm_status.append("   • Status: ❌ LLM service not responding")
            llm_status.append(f"   • Error: {str(e)}")
            test_response = None
        
        # Extract response content for length calculation
        if hasattr(test_response, 'messages') and test_response.messages:
            last_message = test_response.messages[-1]
            response_content = getattr(last_message, 'content', str(last_message))
        else:
            response_content = str(test_response)
        
        llm_status.append(f"   • Response: ✅ Received {len(response_content)} characters")
        
        # 4. MCP Server
        mcp_status = []
        mcp_status.append("☸️ MCP Server:")
        
        # List tools to check MCP server connectivity
        tools = self.client.tools.list()
        
        # Extract unique toolgroup IDs
        toolgroups = list(set(tool.toolgroup_id for tool in tools))
        mcp_status.append("   • Status: ✅ MCP server responding")
        mcp_status.append(f"   • Toolgroups: ✅ Found {len(toolgroups)} toolgroup(s)")
        
        # List all toolgroup identifiers as a simple list
        if toolgroups:
            mcp_status.append("   • Toolgroup IDs:")
            for toolgroup_id in toolgroups:
                mcp_status.append(f"      - {toolgroup_id}")
        
        # Combine all status information
        full_status = "\n".join([
            "=" * 60,
            "🔍 SYSTEM STATUS REPORT",
            "=" * 60,
            "",
            gradio_status,
            "",
            "\n".join(llama_stack_status),
            "",
            "\n".join(llm_status),
            "",
            "\n".join(mcp_status),
            "",
            "=" * 60
        ])
        
        return full_status


def create_demo(chat_tab: ChatTab, mcp_test_tab: MCPTestTab, system_status_tab: SystemStatusTab):
    """Create the beautiful Gradio interface with header and chat"""
    
    with gr.Blocks(
        title="Intelligent CD Chatbot",
        # https://www.gradio.app/guides/theming-guide
        theme=gr.themes.Soft(),  # Fixed light theme - no dark mode switching
        css="""
        /* Full screen responsive layout */
        .gradio-container {
            max-width: 100vw !important;
            width: 100vw !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        
        /* Main content area - full width */
        .main-panel {
            width: 100% !important;
            max-width: 100% !important;
        }
        
        /* Header styling */
        .header-container {
            background: linear-gradient(135deg, #ff8c42 0%, #ffa726 50%, #ff7043 100%);
            color: white;
            padding: 20px;
            border-radius: 0 0 15px 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            width: 100% !important;
        }
        
        .header-content {
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .logo {
            width: 50px;
            height: 50px;
            border-radius: 10px;
        }
        
        .header-title {
            font-size: 2.2em;
            font-weight: bold;
            margin: 0;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }
        
        .header-subtitle {
            font-size: 1.1em;
            opacity: 0.95;
            margin: 5px 0 0 0;
            text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
        }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        /* Chat input and buttons layout */
        .chat-input-container {
            display: flex !important;
            gap: 10px !important;
            align-items: flex-start !important;
            width: 100% !important;
        }
        
        .chat-input-field {
            flex: 1 !important;
            min-width: 0 !important;
        }
        
        .chat-buttons-column {
            display: flex !important;
            flex-direction: column !important;
            gap: 8px !important;
            flex-shrink: 0 !important;
        }
        

        
        /* Ensure both panels have equal heights */
        .equal-height-panels {
            display: flex !important;
            align-items: stretch !important;
        }
        
        /* Status indicator styling */
        .status-ready {
            background-color: #e8f5e8 !important;
            border-color: #4caf50 !important;
            color: #2e7d32 !important;
        }
        
        .status-loading {
            background-color: #fff3e0 !important;
            border-color: #ff9800 !important;
            color: #e65100 !important;
        }
        
        .status-error {
            background-color: #ffebee !important;
            border-color: #f44336 !important;
            color: #c62828 !important;
        }
        
        .status-success {
            background-color: #e8f5e8 !important;
            border-color: #4caf50 !important;
            color: #2e7d32 !important;
        }
        
        /* Responsive adjustments */
        @media (max-width: 768px) {
            .header-title {
                font-size: 1.8em !important;
            }
            .header-subtitle {
                font-size: 1em !important;
            }
        }
        """
    ) as demo:
        
        # Beautiful Header with Logo
        with gr.Row():
            with gr.Column(scale=1):
                gr.HTML("""
                <div class="header-container">
                    <div class="header-content">
                        <div class="header-left">
                            <svg class="logo" version="1.0" xmlns="http://www.w3.org/2000/svg" width="50" height="50" viewBox="0 0 300 300" preserveAspectRatio="xMidYMid meet">
                                <g transform="translate(0.000000,300.000000) scale(0.100000,-0.100000)" fill="currentColor" stroke="none">
                                    <path d="M1470 2449 c-47 -10 -80 -53 -80 -105 0 -45 26 -88 61 -99 18 -6 19 -14 17 -138 l-3 -132 -37 -3 -38 -3 0 48 c0 43 -4 53 -34 82 -32 31 -35 38 -33 87 2 46 -2 57 -27 83 -36 38 -74 46 -120 27 -70 -29 -86 -125 -30 -177 20 -19 36 -24 79 -24 70 0 95 -22 95 -82 l0 -43 -162 0 c-108 -1 -175 -5 -200 -14 -98 -35 -168 -134 -178 -250 l-5 -69 -44 -11 c-69 -17 -85 -47 -90 -164 -5 -147 17 -194 102 -211 l32 -7 5 -80 c4 -64 11 -90 36 -134 50 -88 141 -140 247 -140 l47 0 0 -135 c0 -122 2 -137 20 -155 11 -11 29 -20 40 -20 21 0 31 8 233 193 l129 117 226 0 c125 0 244 5 264 10 62 18 128 71 162 130 25 44 32 70 36 134 l5 79 44 11 c74 18 86 45 86 186 0 141 -12 168 -86 186 l-44 11 -6 74 c-10 113 -58 187 -153 234 -47 24 -59 25 -218 25 l-168 0 0 40 c0 53 38 91 85 83 60 -10 125 46 125 107 0 38 -30 81 -67 96 -45 19 -83 11 -119 -27 -25 -26 -29 -37 -27 -83 2 -49 -1 -56 -33 -87 -30 -29 -34 -39 -34 -82 l0 -48 -37 3 -38 3 -3 132 c-2 124 -1 132 17 138 35 11 61 54 61 99 0 75 -62 122 -140 105z m65 -79 c27 -30 7 -70 -35 -70 -42 0 -62 40 -35 70 10 11 26 20 35 20 9 0 25 -9 35 -20z m-281 -152 c16 -26 -4 -53 -40 -53 -23 0 -30 5 -32 23 -7 47 47 69 72 30z m556 8 c6 -8 10 -25 8 -38 -6 -42 -78 -32 -78 11 0 37 46 55 70 27z m-4 -376 c182 0 193 -1 225 -23 19 -12 44 -42 57 -67 21 -43 22 -54 22 -330 0 -276 -1 -287 -22 -330 -13 -25 -38 -55 -57 -67 -33 -22 -41 -23 -288 -23 l-253 0 -91 -82 c-50 -46 -109 -98 -130 -116 l-39 -34 0 96 c0 130 -6 136 -134 136 -111 0 -147 18 -183 90 -22 43 -23 54 -23 330 0 277 1 287 23 330 25 50 60 79 106 89 17 3 159 5 314 3 155 -1 368 -2 473 -2z"/>
                                    <path d="M1159 1621 c-80 -80 12 -215 114 -166 52 24 74 79 53 129 -30 71 -114 90 -167 37z"/>
                                    <path d="M1702 1625 c-60 -50 -47 -142 24 -171 45 -19 78 -12 115 26 90 89 -42 226 -139 145z"/>
                                    <path d="M1280 1269 c-10 -17 -6 -25 25 -54 91 -86 299 -86 390 0 31 29 35 37 25 54 -15 28 -31 26 -95 -10 -47 -26 -65 -31 -125 -31 -59 0 -78 5 -127 31 -67 37 -79 38 -93 10z"/>
                                </g>
                            </svg>
                            <div>
                                <div class="header-title">Intelligent CD Chatbot</div>
                                <div class="header-subtitle">AI-Powered GitOps Deployment Assistant</div>
                            </div>
                        </div>
                        <div class="header-right">
                            <div style="text-align: right;">
                                <div style="font-size: 0.8em; opacity: 0.7; margin-bottom: 2px;">
                                    Powered by
                                </div>
                                <div style="font-size: 1.2em; font-weight: bold; opacity: 0.9;">
                                    Red Hat AI
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                """)
        
        # Top Right Controls - Removed for cleaner interface
        
        # Main Content Area - Two Columns
        with gr.Row():
            # Left Column - Chatbot (40%)
            with gr.Column(scale=2):
                # Tab system for different interfaces
                with gr.Tabs():
                    # Chat Tab
                    with gr.TabItem("💬 Chat"):
                        # Vertical layout: Chat history (7) and input (3)
                        with gr.Column():
                            # Chat Interface - Takes most of the space (scale 7)
                            with gr.Column(scale=7):
                                history = [gr.ChatMessage(role="assistant", content="Hello, how can I help you?")]
                                
                                chatbot = gr.Chatbot(history,
                                    label="💬 Chat with AI Assistant",
                                    show_label=False,
                                    avatar_images=["assets/chatbot.png", "assets/chatbot.png"],
                                    type="messages",
                                    layout="panel"
                                )
                            
                            # Chat Input - Takes less space (scale 3)
                            with gr.Column(scale=3):
                                msg = gr.Textbox(
                                    label="Message",
                                    show_label=False,
                                    placeholder="Ask me about Kubernetes, GitOps, or OpenShift deployments... (Press Enter to send, Shift+Enter for new line)",
                                    lines=2,
                                    max_lines=4,
                                    submit_btn=True,
                                    stop_btn=True
                                )
                    
                    # MCP Test Tab
                    with gr.TabItem("🧪 MCP Test"):
                        # Status Bar - Simple textbox with status styling
                        status_indicator = gr.Textbox(
                            label="Status",
                            value="✅ Ready to test MCP server",
                            interactive=False,
                            show_label=False,
                            elem_classes=["status-ready"]
                        )
                        
                        # Toolgroup Selector with Refresh Button
                        with gr.Row():
                            refresh_toolgroups_btn = gr.Button("🔄ToolGroups", variant="secondary", size="md", scale=1)
                            refresh_methods_btn = gr.Button("🔄Methods", variant="secondary", size="md", scale=1)

                        toolgroup_selector = gr.Dropdown(
                            choices=["Select a toolgroup..."],
                            label="Select Toolgroup",
                            value="Select a toolgroup...",
                            interactive=True
                        )

                        method_selector = gr.Dropdown(
                            choices=["Select a method..."],
                            label="Select Method",
                            value="Select a method...",
                            interactive=True
                        )

                        
                        # Parameters Section
                        with gr.Group():
                            # gr.Markdown("**Parameters:**")
                            params_input = gr.Textbox(
                                label="Parameters (JSON)",
                                placeholder='{"namespace": "default"}',
                                lines=3,
                                value='{}'
                            )
                        
                        # Execute Button
                        execute_btn = gr.Button("Execute Method", variant="primary", size="lg")
                    
                    # System Status Tab
                    with gr.TabItem("🔍 System Status"):
                        # Check Status Button
                        check_status_btn = gr.Button("Check System Status", variant="primary", size="lg")
                        
                        # Note for user
                        gr.Markdown("Click the button above to view detailed system information in the right panel.")
            
            # Right Column - Code Canvas (60%)
            with gr.Column(scale=3):
                # Dynamic content area for System Status, MCP Test results, and other content
                content_area = gr.Textbox(
                    label="📝 Code Canvas",
                    placeholder="Click a button above to see results here, or chat with the AI to generate deployment manifests...",
                    lines=20,
                    max_lines=50,
                    interactive=False,
                    show_copy_button=True,
                    show_label=True
                )
        

        
        # Event handlers     
        # Refresh Toolgroups Button (next to dropdown)
        refresh_toolgroups_btn.click(
            fn=mcp_test_tab.list_toolgroups,
            outputs=[toolgroup_selector]
        )
        
        # Refresh Methods Button
        refresh_methods_btn.click(
            fn=mcp_test_tab.get_toolgroup_methods,
            inputs=[toolgroup_selector],
            outputs=[status_indicator, method_selector]
        )
        
        execute_btn.click(
            fn=lambda toolgroup, method, params: f"🧪 MCP Method Execution: {method}\n\n{mcp_test_tab.execute_tool(toolgroup, method, params)}",
            inputs=[toolgroup_selector, method_selector, params_input],
            outputs=content_area
        )
        
        # System Status Tab functionality
        check_status_btn.click(
            fn=lambda: f"{system_status_tab.get_system_status()}",
            outputs=content_area
        )
        
        # Chat functionality - using built-in submit button
        msg.submit(
            fn=chat_tab.chat_completion,
            inputs=[msg, chatbot],
            outputs=[chatbot, msg]
        )
        

    
    return demo


def initialize_llama_stack_client() -> tuple[LlamaStackClient, ChatTab, MCPTestTab, SystemStatusTab]:
    """Initialize Llama Stack client and all tab classes"""
    # Get logger for initialization
    logger = get_logger("init")
    
    # ALL CONFIGURATION IN ONE PLACE - including environment variable reading
    llama_stack_url = os.getenv("LLAMA_STACK_URL", "http://localhost:8321")
    model = os.getenv("DEFAULT_LLM_MODEL", "llama-3-2-3b")
    
    logger.info("=" * 60)
    logger.info("INITIALIZING LLAMA STACK CLIENT")
    logger.info("=" * 60)
    
    # Log environment variables
    logger.info("Environment Variables:")
    logger.info(f"  LLAMA_STACK_URL: {os.getenv('LLAMA_STACK_URL', 'Not set (using default)')}")
    logger.info(f"  DEFAULT_LLM_MODEL: {os.getenv('DEFAULT_LLM_MODEL', 'Not set (using default)')}")
    
    # Log final configuration
    logger.info("Final Configuration:")
    logger.info(f"  Llama Stack URL: {llama_stack_url}")
    logger.info(f"  Model: {model}")
    
    llama_stack_client = LlamaStackClient(base_url=llama_stack_url)
    logger.info(f"Llama Stack client initialized successfully with URL: {llama_stack_url}")
    
    # Define sampling parameters - ALL CONFIGURATION IN ONE PLACE
    sampling_params = {
        "temperature": 0.7,
        "max_tokens": 4096,
        "strategy": {"type": "greedy"}  # Added strategy like in the working example
    }
    
    # Configuration for builtin tools
    enable_builtin_tools = os.getenv("ENABLE_BUILTIN_TOOLS", "false").lower() == "true"
    
    logger.info("=" * 60)
    logger.info(f"Builtin tools enabled: {enable_builtin_tools}")
    if enable_builtin_tools:
        logger.info("Note: Builtin tools require API keys (TAVILY_SEARCH_API_KEY, etc.)")
    
    # Initialize tab classes with shared client
    chat_tab = ChatTab(llama_stack_client, model=model, sampling_params=sampling_params, enable_builtin_tools=enable_builtin_tools)
    mcp_test_tab = MCPTestTab(llama_stack_client)
    system_status_tab = SystemStatusTab(llama_stack_client, llama_stack_url, model=model)
    
    logger.info("All tab classes initialized successfully")
    logger.info("=" * 60)
    return llama_stack_client, chat_tab, mcp_test_tab, system_status_tab

def main():
    """Main function to launch the Gradio app"""
    # Initialize Llama Stack client and tab classes
    llama_stack_client, chat_tab, mcp_test_tab, system_status_tab = initialize_llama_stack_client()
    
    # Create the Gradio demo with tab instances
    demo = create_demo(chat_tab, mcp_test_tab, system_status_tab)
    
    # Launch the app
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True,
        show_error=True
    )


if __name__ == "__main__":
    main()
