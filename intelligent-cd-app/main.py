import gradio as gr
import json
import os
import logging
from typing import List, Dict
from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.react.agent import ReActAgent
from llama_stack_client.lib.agents.react.tool_parser import ReActOutput

"""
Intelligent CD Chatbot - Production-Ready Logging Configuration

This application uses Python's built-in logging module for professional logging.

Environment Variables for Logging:
- LOG_LEVEL: Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL). Default: INFO

Environment Variables for Tools:
- TOOLGROUPS_DENYLIST: JSON array of toolgroup IDs to exclude (e.g., '["builtin::websearch", "mcp::argocd"]')
- TAVILY_SEARCH_API_KEY: API key for websearch tool (if using builtin tools)
- Other API keys as needed for builtin tools

Environment Variables for MCP Server Authentication:
- ARGOCD_BASE_URL: Base URL of the ArgoCD server (e.g., "https://argocd.example.com")
- ARGOCD_API_TOKEN: API token for ArgoCD server authentication

Examples:
  export LOG_LEVEL=DEBUG    # Enable verbose debugging
  export TOOLGROUPS_DENYLIST='["builtin::websearch", "mcp::argocd"]'  # Exclude specific toolgroups
  export ARGOCD_BASE_URL="https://argocd.example.com"  # ArgoCD base URL
  export ARGOCD_API_TOKEN="your-argocd-token"  # ArgoCD API token
  
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


model_prompt = """<|begin_of_text|><|header_start|>system<|header_end|>

You are an expert software engineer and DevOps specialist powered by ReAct (Reason-then-Act) methodology. Your primary goal is to help users understand, configure, and troubleshoot Kubernetes/OpenShift application systems through systematic reasoning and intelligent tool usage.

**ReAct Reasoning Framework:**

1. **REASON:** Before taking any action, clearly think through:
   - What information do I need to solve this problem?
   - Which MCP tools are most appropriate for gathering this information?
   - What is my step-by-step approach to address the user's request?

2. **ACT:** Execute your reasoning by using the appropriate tools:
   - Use MCP tools for real-time cluster data, pod status, logs, and system information
   - Use builtin::rag to search knowledge base for configuration guides, troubleshooting procedures, and best practices
   - Combine multiple tools when needed to get complete information

3. **OBSERVE:** Analyze the results from your actions and determine:
   - Did I get the information I need?
   - Do I need additional data or clarification?
   - What patterns or issues can I identify?

4. **REASON AGAIN:** Based on observations, determine next steps:
   - Continue gathering more specific information
   - Synthesize findings into actionable recommendations
   - Provide clear explanations and solutions

**Standard Operating Procedure for Problem Solving:**

When a user reports application issues (API failures, database problems, performance issues, etc.):
- **REASON**: Break down the problem into specific diagnostic steps
- **ACT**: Use MCP tools systematically to gather both real-time system data AND documentation
- **OBSERVE**: Analyze results and correlate system state with known patterns
- **REASON & ACT**: Provide synthesized recommendations with supporting evidence

**Your Expertise Areas:**
- Kubernetes/OpenShift cluster management and troubleshooting
- Application deployment and configuration troubleshooting
- GitOps workflows and deployment strategies
- System monitoring, logging, and performance analysis
- Container orchestration and pod diagnostics
- Service mesh and networking troubleshooting

**Available Tools:** {tool_groups}

**Key Principles:**
- Always use tool_calls to execute MCP functions for real cluster data
- Never generate fake data or describe hypothetical scenarios when real data is available
- Combine real-time system data with knowledge base searches for comprehensive solutions
- Provide clear, actionable guidance based on both real-time data and documented best practices
- Be helpful but don't over-explain when users just want quick answers

**CRITICAL**: When you need to use tools, set "answer": null in your response. Only provide "answer" with actual results after tool execution is complete.

You're connected to a real cluster - use the tools to get real information.<|eot|><|header_start|>user<|header_end|>"""

class ChatTab:
    """Handles chat functionality with Llama Stack LLM"""
    
    def __init__(self, client: LlamaStackClient, model: str, vector_db_id: str):
        self.client = client
        self.model = model
        self.vector_db_id = vector_db_id
        self.logger = get_logger("chat")
        self.sampling_params = {"temperature": 0.1, "max_tokens": 4096, "max_new_tokens": 4096, "strategy": {"type": "greedy"} }

        # Initialize available tools once during initialization
        self.tools_array = self._get_available_tools()
        
        # Initialize agent and session for the entire chat
        self.agent, self.session_id = self._initialize_agent()

    
    def _get_available_tools(self) -> list:
        """Get available tools and filter based on denylist configuration"""
        tools = self.client.tools.list()
        tool_groups = list(set(tool.toolgroup_id for tool in tools))
        
        # Get denylist from environment variable
        denylist_str = os.getenv("TOOLGROUPS_DENYLIST", "")
        denylist = []
        if denylist_str:
            try:
                import json
                denylist = json.loads(denylist_str)
            except json.JSONDecodeError:
                self.logger.warning(f"Invalid TOOLGROUPS_DENYLIST format: {denylist_str}")
        
        # Filter out denylisted toolgroups
        filtered_tool_groups = [tg for tg in tool_groups if tg not in denylist]

        # Always add the RAG tool configuration as a dictionary to the filtered_tool_groups list
        # https://llama-stack.readthedocs.io/en/latest/building_applications/rag.html
        # filtered_tool_groups.append({"name": "builtin::rag", "args": {"vector_db_ids":  ["self.vector_db_id"], "top_k": 5}})
        
        self.logger.info(f"Filtered tool groups: {filtered_tool_groups}")
        if denylist:
            self.logger.info(f"Tools: {len(filtered_tool_groups)}/{len(tool_groups)} available (filtered)")
        else:
            self.logger.info(f"Tools: {len(tool_groups)} available (no filtering)")
        
        return filtered_tool_groups
    
    def _initialize_agent(self) -> tuple[ReActAgent, str]:
        """Initialize agent and session that will be reused for the entire chat"""
        
        formatted_prompt = model_prompt.format(tool_groups=self.tools_array)

        # Log agent creation details
        self.logger.info("=" * 60)
        self.logger.info("CREATING ReActAgent")
        self.logger.info("=" * 60)
        self.logger.info(f"Model: {self.model}")
        self.logger.info(f"Toolgroups available ({len(self.tools_array)}): {self.tools_array}")
        self.logger.info(f"Sampling params: {self.sampling_params}")

        agent = ReActAgent(
            client=self.client,
            model=self.model,
            instructions=formatted_prompt,
            tools=self.tools_array,
            tool_config={"tool_choice": "auto"},  # Ensure tools are actually executed
            response_format={
                "type": "json_schema",
                "json_schema": ReActOutput.model_json_schema(),
            },
            sampling_params=self.sampling_params
        )
        
        self.logger.info("✅ ReActAgent created successfully")

        # Create session for the agent
        session = agent.create_session(session_name="OCP_Chat_Session")
        
        # Handle both object with .id attribute and direct string return
        if hasattr(session, 'id'):
            session_id = session.id
        else:
            session_id = str(session)
        
        self.logger.info(f"✅ Session created: {session_id}")
        self.logger.info("=" * 60)
        return agent, session_id
    
    def chat_completion(self, message: str, chat_history: List[Dict[str, str]]) -> tuple:
        """Handle chat with LLM using Agent → Session → Turn structure"""
        from gradio import ChatMessage
        
        # Add user message to history
        chat_history.append(ChatMessage(role="user", content=message))
        
        # Get LLM response using Agent API with thinking steps
        result, thinking_steps = self._execute_agent_turn_with_thinking(message)
        
        # Add thinking steps as collapsible sections
        if thinking_steps:
            for i, step in enumerate(thinking_steps):
                chat_history.append(ChatMessage(
                    role="assistant", 
                    content=step["content"],
                    metadata={"title": step["title"]}
                ))
        
        # Add final assistant response
        chat_history.append(ChatMessage(role="assistant", content=result))
        
        return chat_history, ""
    
    def _execute_agent_turn_with_thinking(self, message: str) -> tuple[str, list]:
        """Execute agent turn and capture thinking steps for display"""
        import json
        self.logger.debug(f"Executing agent turn with thinking capture")
        
        thinking_steps = []
        
        try:
            response = self.agent.create_turn(
                messages=[
                    {
                        "role": "user",
                        "content": message
                    }
                ],
                session_id=self.session_id,
                stream=False,  # Keep non-streaming for now
            )
            
            # Debug: Print response structure (keep for logging)
            self.logger.info(f"Response type: {type(response)}")
            self.logger.info(f"Response attributes: {dir(response)}")
            
            # Extract thinking steps from response.steps if available
            if hasattr(response, 'steps') and response.steps:
                self.logger.info(f"Found {len(response.steps)} steps")
                for i, step in enumerate(response.steps):
                    self.logger.info(f"Step {i}: {type(step)} - {dir(step)}")
                    
                    # Parse ReActAgent step structure
                    step_content = ""
                    step_title = f"Step {i+1}"
                    
                    # Check if this is an InferenceStep with api_model_response
                    if hasattr(step, 'api_model_response') and hasattr(step.api_model_response, 'content'):
                        try:
                            # Parse the JSON content from the ReActAgent response
                            content_json = json.loads(step.api_model_response.content)
                            
                            # Extract thought if available
                            if 'thought' in content_json and content_json['thought']:
                                step_content = content_json['thought']
                                step_title = "🧠 Thinking"
                                thinking_steps.append({
                                    "title": step_title,
                                    "content": step_content.strip()
                                })
                            
                            # Extract action if available
                            if 'action' in content_json and content_json['action']:
                                action = content_json['action']
                                if isinstance(action, dict) and 'tool_name' in action:
                                    action_content = f"Using tool: {action['tool_name']}"
                                    if 'tool_params' in action and action['tool_params']:
                                        params_str = ", ".join([f"{p.get('name', 'param')}={p.get('value', '')}" for p in action['tool_params']])
                                        action_content += f" with parameters: {params_str}"
                                    
                                    thinking_steps.append({
                                        "title": "🔧 Action",
                                        "content": action_content
                                    })
                            
                            # Extract answer if available (this will be the final response)
                            if 'answer' in content_json and content_json['answer']:
                                step_content = content_json['answer']
                                step_title = "📋 Result"
                                thinking_steps.append({
                                    "title": step_title,
                                    "content": step_content.strip()
                                })
                                
                        except json.JSONDecodeError as e:
                            self.logger.warning(f"Failed to parse JSON content from step {i}: {e}")
                            # Fallback to string representation
                            step_content = str(step.api_model_response.content)
                            thinking_steps.append({
                                "title": f"💭 Step {i+1}",
                                "content": step_content.strip()
                            })
                    
                    # Fallback: try other content attributes
                    elif hasattr(step, 'content'):
                        step_content = str(step.content)
                        thinking_steps.append({
                            "title": f"💭 Step {i+1}",
                            "content": step_content.strip()
                        })
            
            # Get final response content - extract only the answer part
            final_content = ""
            if hasattr(response, 'output_message') and hasattr(response.output_message, 'content'):
                try:
                    # Try to parse as JSON to extract just the answer
                    content_json = json.loads(response.output_message.content)
                    if 'answer' in content_json and content_json['answer']:
                        final_content = content_json['answer']
                    else:
                        final_content = response.output_message.content
                except json.JSONDecodeError:
                    # If not JSON, use the content as-is
                    final_content = response.output_message.content
            else:
                final_content = str(response)
            
            self.logger.info(f"Captured {len(thinking_steps)} thinking steps")
            self.logger.info(f"Final content length: {len(final_content)} characters")
            return final_content, thinking_steps
            
        except Exception as e:
            self.logger.error(f"Error in agent turn: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error: {str(e)}", []
    

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
                kwargs=params,
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


class RAGTestTab:
    """Handles RAG testing functionality"""
    
    def __init__(self, client: LlamaStackClient, vector_db_id: str):
        self.client = client
        self.logger = get_logger("rag")
        self.vector_db_id = vector_db_id

    def test_rag(self, query: str) -> str:
        """Test RAG functionality and report status in a user-friendly way"""

        self.logger.info(f"RAG Query:\n\n{query}")

        try:
            # Query documents
            result = self.client.tool_runtime.rag_tool.query(
                vector_db_ids=[self.vector_db_id],
                content=query,
            )
            self.logger.debug(f"RAG Result:\n\n{result}")

            # Try to format the result nicely for the user
            if isinstance(result, (dict, list)):
                formatted_result = json.dumps(result, indent=2)
            else:
                formatted_result = str(result)

            return (
                f"✅ RAG Query executed successfully!\n\n"
                f"**Query:**\n{query}\n\n"
                f"**Result:**\n```\n{formatted_result}\n```"
            )
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.logger.error(f"RAG Query failed: {str(e)}\n{tb}")
            return (
                f"❌ RAG Query failed!\n\n"
                f"**Query:**\n{query}\n\n"
                f"**Error:**\n{str(e)}\n\n"
                f"**Traceback:**\n```\n{tb}\n```"
            )

    def get_rag_status(self) -> str:
        """Get detailed RAG status information including providers, databases, and documents"""
        
        self.logger.info("Getting detailed RAG status information...")
        
        status_info = []
        status_info.append("=" * 60)
        status_info.append("📚 RAG STATUS REPORT")
        status_info.append("=" * 60)
        status_info.append("")
        
        try:
            # 1. List all available vector databases (summary only)
            status_info.append("🗄️ **Vector Databases:**")
            try:
                vector_dbs = self.client.vector_dbs.list()
                if vector_dbs:
                    for db_item in vector_dbs:
                        if hasattr(db_item, 'identifier'):
                            db_id = db_item.identifier
                            current_marker = " ✅ (Currently configured)" if db_id == self.vector_db_id else ""
                            status_info.append(f"   • {db_id}{current_marker}")
                        else:
                            status_info.append(f"   • {str(db_item)}")
                else:
                    status_info.append("   • No vector databases found")
            except Exception as e:
                status_info.append(f"   ❌ Error listing vector databases: {str(e)}")
            
            status_info.append("")
            
            # 2. Get detailed information about the configured vector database
            if self.vector_db_id:
                status_info.append(f"🔍 **Detailed Information for '{self.vector_db_id}':**")
                
                # Try to get database info using the correct API
                try:
                    db_info = self.client.vector_dbs.retrieve(self.vector_db_id)
                    if db_info:
                        if hasattr(db_info, '__dict__'):
                            for key, value in db_info.__dict__.items():
                                if not key.startswith('_') and value is not None:
                                    status_info.append(f"   • {key.replace('_', ' ').title()}: {value}")
                        else:
                            status_info.append(f"   • Database Info: {str(db_info)}")
                    else:
                        status_info.append("   • No detailed database information available")
                except Exception as e:
                    status_info.append(f"   ❌ Error getting database info: {str(e)}")
                
                status_info.append("")
                
                # 3. Get document information with count and truncated titles
                status_info.append(f"📄 **Documents in '{self.vector_db_id}':**")
                try:
                    # Try to get document information through queries
                    document_titles = []
                    document_count = 0
                    
                    # Try different queries to extract document information
                    test_queries = [
                        "What documents are available?",
                        "List all document titles",
                        "What files or documents are stored?",
                        "Show me the document names"
                    ]
                    
                    for query in test_queries:
                        try:
                            result = self.client.tool_runtime.rag_tool.query(
                                vector_db_ids=[self.vector_db_id],
                                content=query,
                            )
                            if result:
                                result_str = str(result).lower()
                                # Look for document-related information in the response
                                if any(keyword in result_str for keyword in ['document', 'file', 'title', 'name']):
                                    # Try to extract titles from the response
                                    lines = str(result).split('\n')
                                    for line in lines:
                                        line = line.strip()
                                        if line and len(line) > 5 and len(line) < 100:
                                            # Simple heuristic to identify potential document titles
                                            if any(keyword in line.lower() for keyword in ['document', 'file', '.pdf', '.txt', '.doc', 'title']):
                                                if line not in document_titles:
                                                    document_titles.append(line)
                                    break
                        except Exception:
                            continue
                    
                    # If we couldn't extract titles, try a more generic approach
                    if not document_titles:
                        try:
                            # Try to get a sample of content to estimate document count
                            sample_result = self.client.tool_runtime.rag_tool.query(
                                vector_db_ids=[self.vector_db_id],
                                content="sample content",
                            )
                            if sample_result:
                                # Estimate based on response length and structure
                                result_str = str(sample_result)
                                if len(result_str) > 1000:
                                    document_count = "Multiple documents detected"
                                else:
                                    document_count = "Documents available"
                        except Exception:
                            pass
                    
                    # Display results
                    if document_titles:
                        status_info.append(f"   • Document Count: {len(document_titles)} documents found")
                        status_info.append("   • Document Titles (truncated):")
                        for i, title in enumerate(document_titles[:5]):  # Show max 5 titles
                            truncated_title = title[:60] + "..." if len(title) > 60 else title
                            status_info.append(f"     {i+1}. {truncated_title}")
                        if len(document_titles) > 5:
                            status_info.append(f"     ... and {len(document_titles) - 5} more documents")
                    elif document_count:
                        status_info.append(f"   • Document Status: {document_count}")
                    else:
                        status_info.append("   • Document information not available through queries")
                        status_info.append("   • System is responsive to queries")
                        
                except Exception as e:
                    status_info.append(f"   ❌ Error accessing document information: {str(e)}")
                
                status_info.append("")
                
                # 4. Provider information (extracted from vector databases)
                status_info.append("🔧 **Provider Information:**")
                try:
                    vector_dbs = self.client.vector_dbs.list()
                    providers_found = set()
                    for db_item in vector_dbs:
                        if hasattr(db_item, 'provider_id'):
                            providers_found.add(db_item.provider_id)
                    
                    if providers_found:
                        status_info.append("   • Configured Providers:")
                        for provider in providers_found:
                            status_info.append(f"     • {provider}")
                    else:
                        status_info.append("   • No provider information available")
                        
                except Exception as e:
                    status_info.append(f"   ❌ Error getting provider info: {str(e)}")
                
                status_info.append("")
                
                # 5. Functionality test
                status_info.append("🧪 **Functionality Test:**")
                try:
                    test_result = self.client.tool_runtime.rag_tool.query(
                        vector_db_ids=[self.vector_db_id],
                        content="test query",
                    )
                    if test_result:
                        status_info.append("   ✅ RAG query functionality is working")
                        status_info.append(f"   • Test query returned: {len(str(test_result))} characters")
                    else:
                        status_info.append("   ⚠️ RAG query returned empty result")
                except Exception as e:
                    status_info.append(f"   ❌ RAG query test failed: {str(e)}")
            
            else:
                status_info.append("❌ No vector database ID configured")
            
            status_info.append("")
            status_info.append("=" * 60)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.logger.error(f"RAG Status check failed: {str(e)}\n{tb}")
            status_info.append(f"❌ Error getting RAG status: {str(e)}")
            status_info.append("")
            status_info.append("**Traceback:**")
            status_info.append(f"```\n{tb}\n```")
            status_info.append("")
            status_info.append("=" * 60)
        
        return "\n".join(status_info)


class SystemStatusTab:
    """Handles system status functionality"""
    
    def __init__(self, client: LlamaStackClient, llama_stack_url: str, model: str, vector_db_id: str):
        self.client = client
        self.llama_stack_url = llama_stack_url
        self.model = model
        self.vector_db_id = vector_db_id
        self.logger = get_logger("system")  
    
    def get_gradio_status(self) -> str:
        """Get Gradio application status"""
        return "✅ Gradio Application: Running and accessible"
    
    def get_llama_stack_status(self) -> list[str]:
        """Get Llama Stack server health and version information"""
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
        
        return llama_stack_status
    
    def get_llm_status(self) -> list[str]:
        """Get LLM service status and test connectivity"""
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
        
        return llm_status
    
    def get_rag_status(self) -> list[str]:
        """Get RAG server status and vector database availability"""
        rag_status = []
        rag_status.append("📚 RAG Server:")
        
        # Check 1: Test connection by calling list()
        try:
            rag_vector_dbs = self.client.vector_dbs.list()
            rag_status.append("   • Connection: ✅ RAG backend responding")
        except Exception as e:
            rag_status.append("   • Connection: ❌ Failed to connect to RAG backend")
            rag_status.append(f"   • Error: {str(e)}")
            return rag_status
        
        # Check 2: Show if self.vector_db_id is included in the list
        vector_db_ids = [db.identifier for db in rag_vector_dbs] if rag_vector_dbs else []
        if self.vector_db_id in vector_db_ids:
            rag_status.append(f"   • Target DB: ✅ Vector DB '{self.vector_db_id}' found in list")
        else:
            rag_status.append(f"   • Target DB: ❌ Vector DB '{self.vector_db_id}' not found in list")
        
        # Check 3: Show all identifiers from the list
        if vector_db_ids:
            rag_status.append(f"   • Available DBs: Found {len(vector_db_ids)} vector database(s)")
            rag_status.append("   • DB Identifiers:")
            for db_id in vector_db_ids:
                rag_status.append(f"      - {db_id}")
        else:
            rag_status.append("   • Available DBs: No vector databases found")

        return rag_status
    
    def get_mcp_status(self) -> list[str]:
        """Get MCP server status and tool information"""
        mcp_status = []
        mcp_status.append("☸️ MCP Server:")
        
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
        
        return mcp_status
    
    def get_system_status(self) -> str:
        """Get comprehensive system status by combining all component statuses"""
        
        # Combine all status information
        full_status = "\n".join([
            "=" * 60,
            "🔍 SYSTEM STATUS REPORT",
            "=" * 60,
            "",
            self.get_gradio_status(),
            "",
            "\n".join(self.get_llama_stack_status()),
            "",
            "\n".join(self.get_llm_status()),
            "",
            "\n".join(self.get_rag_status()),
            "",
            "\n".join(self.get_mcp_status()),
            "",
            "=" * 60
        ])
        
        return full_status


def create_demo(chat_tab: ChatTab, mcp_test_tab: MCPTestTab, rag_test_tab: RAGTestTab, system_status_tab: SystemStatusTab):
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
        
        /* Chat input row styling */
        .chat-input-row {
            display: flex !important;
            align-items: flex-end !important;
            gap: 10px !important;
            width: 100% !important;
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
                                from gradio import ChatMessage
                                history = [ChatMessage(role="assistant", content="Hello, how can I help you?")]
                                
                                chatbot = gr.Chatbot(history,
                                    label="💬 Chat with AI Assistant",
                                    show_label=False,
                                    avatar_images=["assets/chatbot.png", "assets/chatbot.png"],
                                    allow_file_downloads=True,
                                    type="messages",
                                    layout="panel"
                                )
                            
                            # Chat Input - Takes less space (scale 3)
                            with gr.Column(scale=3):
                                with gr.Row():
                                    with gr.Column(scale=6):
                                        msg = gr.Textbox(
                                            label="Message",
                                            show_label=False,
                                            placeholder="Ask me about Kubernetes, GitOps, or OpenShift deployments...",
                                            value="Using the resources_list tool from the MCP Server for OpenShift, list the pods in the namespace intelligent-cd and show the name, container image and status of each pod.",
                                            lines=2,
                                            max_lines=3
                                        )
                                    with gr.Column(scale=2):
                                        send_btn = gr.Button("Send", variant="primary", size="md", scale=1)
                                        save_btn = gr.Button("Save", variant="primary", size="md", scale=1)
                    
                    # MCP Test Tab
                    with gr.TabItem("🤖 MCP Test"):
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
                    
                    # RAG Test Tab
                    with gr.TabItem("📚 RAG Test"):
                        # Preconfigured textbox
                        rag_input = gr.Textbox(
                            label="RAG Query",
                            value="Based on the documents stored in the RAG, please, tell me which teams and emails I need to contact to approve that my system is not stateless and I also need a route",
                            lines=4,
                            max_lines=6,
                            interactive=True,
                            show_label=True
                        )
                        
                        # Send button
                        rag_send_btn = gr.Button("Send Query", variant="primary", size="lg")
                        
                        # RAG Status button
                        rag_status_btn = gr.Button("RAG Status", variant="secondary", size="lg")
                        
                        # Note for user
                        gr.Markdown("Use the textbox above to modify your RAG query, then click Send to process it. Use RAG Status to view detailed RAG configuration information.")
                    
                    # System Status Tab
                    with gr.TabItem("🔍 System Status"):
                        # Check Status Button
                        system_status_btn = gr.Button("Check System Status", variant="primary", size="lg")
                        
                        # Note for user
                        gr.Markdown("Click the button above to view detailed system information in the right panel.")
            
            # Right Column - Code Canvas (60%)
            with gr.Column(scale=3):
                # Dynamic content area for System Status, MCP Test results, and other content
                content_area = gr.Textbox(
                    label="📝 Code Canvas & Saved Responses",
                    placeholder="Click a button above to see results here, chat with the AI to generate deployment manifests, or use the Save button to move the last chat response here for better clarity...",
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
        system_status_btn.click(
            fn=lambda: f"{system_status_tab.get_system_status()}",
            outputs=content_area
        )
        
        # RAG Test Tab functionality
        rag_send_btn.click(
            fn=rag_test_tab.test_rag,
            inputs=[rag_input],
            outputs=content_area
        )
        
        # RAG Status button functionality
        rag_status_btn.click(
            fn=rag_test_tab.get_rag_status,
            outputs=content_area
        )
        
        # Chat functionality - both Enter key and Send button
        msg.submit(
            fn=chat_tab.chat_completion,
            inputs=[msg, chatbot],
            outputs=[chatbot, msg]
        )
        
        send_btn.click(
            fn=chat_tab.chat_completion,
            inputs=[msg, chatbot],
            outputs=[chatbot, msg]
        )
        
        # Save button functionality - moves last chat answer to right panel
        save_btn.click(
            fn=lambda chat_history: f"💾 SAVED CHAT RESPONSE:\n\n{chat_history[-1]['content'] if chat_history and len(chat_history) > 0 else 'No chat history available'}",
            inputs=[chatbot],
            outputs=[content_area]
        )
        
        # Add JavaScript to handle Enter key behavior properly
        demo.load(
            fn=None,
            js="""
            function() {
                // Wait for the page to load and find the textarea
                setTimeout(function() {
                    const textarea = document.querySelector('textarea[placeholder*="Ask me about Kubernetes"]');
                    if (textarea) {
                        textarea.addEventListener('keydown', function(e) {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                // Find and click the send button
                                const sendBtn = document.querySelector('button:has-text("Send")');
                                if (sendBtn) {
                                    sendBtn.click();
                                }
                            }
                        });
                        console.log('Enter key handler attached to chat textarea');
                    } else {
                        console.log('Chat textarea not found');
                    }
                }, 1000);
            }
            """
        )
        

    
    return demo


def get_extra_headers_config() -> dict:
    """Configure MCP server authentication headers and return them"""
    argocd_url = os.getenv("ARGOCD_BASE_URL")
    argocd_token = os.getenv("ARGOCD_API_TOKEN")
    
    # Both variables must be defined for MCP authentication to work
    if not argocd_url or not argocd_token:
        return {}
    
    # Both are defined, create headers array
    else:
        headers = {
            "X-LlamaStack-Provider-Data": json.dumps(
                {
                    "mcp_headers": {
                        "http://argocd-mcp-server:3000/sse": {
                            "x-argocd-base-url": argocd_url,
                            "x-argocd-api-token": argocd_token
                        },
                    },
                }
            )
        }
        return headers


def initialize_client() -> tuple[LlamaStackClient, ChatTab, MCPTestTab, RAGTestTab, SystemStatusTab]:
    """Initialize Llama Stack client and all tab classes"""
    # Get logger for initialization
    logger = get_logger("init")
    
    # ALL CONFIGURATION IN ONE PLACE - including environment variable reading
    llama_stack_url = os.getenv("LLAMA_STACK_URL", "http://localhost:8321")
    
    logger.info("=" * 60)
    logger.info("INITIALIZING LLAMA STACK CLIENT")
    logger.info("=" * 60)

    extra_headers = get_extra_headers_config()
    logger.info(f"Extra headers: {extra_headers}")

    # Initialize client and tabs
    llama_stack_client = LlamaStackClient(
        base_url=llama_stack_url,
        default_headers=extra_headers
    )

    vector_db_id = os.getenv("VECTOR_DB_ID", "my_documents")
    models = llama_stack_client.models.list()
    first_model = next(m.identifier for m in models if m.model_type == "llm")
    model = os.getenv("DEFAULT_LLM_MODEL", first_model)

    # Log configuration summary
    logger.info(f"Configuration: URL={llama_stack_url}, Model={model}")
    
    chat_tab = ChatTab(llama_stack_client, model=model, vector_db_id=vector_db_id)
    mcp_test_tab = MCPTestTab(llama_stack_client)
    rag_test_tab = RAGTestTab(llama_stack_client, vector_db_id)
    system_status_tab = SystemStatusTab(llama_stack_client, llama_stack_url, model=model, vector_db_id=vector_db_id)
    
    logger.info("✅ All components initialized successfully")
    logger.info("=" * 60)
    return chat_tab, mcp_test_tab, rag_test_tab, system_status_tab


def main():
    """Main function to launch the Gradio app"""
    # Initialize Llama Stack client and tab classes
    chat_tab, mcp_test_tab, rag_test_tab, system_status_tab = initialize_client()
    
    # Create the Gradio demo with tab instances
    demo = create_demo(chat_tab, mcp_test_tab, rag_test_tab, system_status_tab)
    
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
