# 🚀 Llama Stack Web UI

A simple web interface to access Llama Stack for LLM and Agent interactions with OpenShift.

## Features

- **💬 Chat Interface**: Chat with AI assistant using Llama Stack LLM
- **🧪 MCP Testing**: Test and execute MCP tools through Llama Stack
- **🔍 System Status**: Monitor Llama Stack connectivity and health
- **☸️ OpenShift Integration**: Access Kubernetes/OpenShift resources via MCP

## Prerequisites

- Python 3.11+
- Docker (optional)
- Llama Stack deployment running
- Port forwarding: `oc port-forward service/llama-stack-service 8321:8321`

## Quick Start

### Run Locally

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python main.py
   ```

3. **Access the UI:**
   Open http://localhost:7860

### Run with Docker

1. **Build the image:**
   ```bash
   docker build -t llama-stack-ui .
   ```

2. **Run the container:**
   ```bash
   docker run -p 7860:7860 llama-stack-ui
   ```

3. **Access the UI:**
   Open http://localhost:7860

## Configuration

Set environment variables (optional):
```bash
LLAMA_STACK_URL=http://localhost:8321  # Default
DEFAULT_LLM_MODEL=llama-3-2-3b  # Default
```

## Usage

1. **Chat Tab**: Ask questions about Kubernetes, GitOps, or OpenShift
2. **MCP Test Tab**: Test and execute MCP tools for OpenShift operations
3. **System Status Tab**: Check Llama Stack connectivity and health

## Troubleshooting

- **Connection failed**: Ensure Llama Stack is running and port forwarding is active
- **MCP tools not found**: Verify MCP server is properly configured in Llama Stack
- **LLM errors**: Check if the specified model is available in your Llama Stack deployment
