"""
Chat tab functionality for Intelligent CD Chatbot.

This module handles the main chat interface with LLM using ReAct methodology.
"""

import os
import json
from typing import List, Dict
from llama_stack_client import LlamaStackClient
from llama_stack_client.lib.agents.react.agent import ReActAgent
from llama_stack_client.lib.agents.react.tool_parser import ReActOutput
from utils import get_logger


# Model prompt template
MODEL_PROMPT = """<|begin_of_text|><|header_start|>system<|header_end|>

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
        filtered_tool_groups.append({"name": "builtin::rag", "args": {"vector_db_ids":  [self.vector_db_id], "top_k": 5}})
        
        self.logger.info(f"Filtered tool groups: {filtered_tool_groups}")
        if denylist:
            self.logger.info(f"Tools: {len(filtered_tool_groups)}/{len(tool_groups)} available (filtered)")
        else:
            self.logger.info(f"Tools: {len(tool_groups)} available (no filtering)")
        
        return filtered_tool_groups
    
    def _initialize_agent(self) -> tuple[ReActAgent, str]:
        """Initialize agent and session that will be reused for the entire chat"""
        
        formatted_prompt = MODEL_PROMPT.format(tool_groups=self.tools_array)

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
