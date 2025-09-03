# 🚀 Intelligent CD Web UI

A simple web interface to access Llama Stack for LLM and Agent interactions with OpenShift.

## Features

- **💬 Chat Interface**: Chat with AI assistant using Llama Stack LLM
- **🧪 MCP Testing**: Test and execute MCP tools through Llama Stack
- **🔍 System Status**: Monitor Llama Stack connectivity and health
- **☸️ OpenShift Integration**: Access Kubernetes/OpenShift resources via MCP

## Prerequisites

- Python 3.11+
- Podman (optional)
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
   gradio main.py
   ```

3. **Access the UI:**
   Open http://localhost:7860/?__theme=light



```bash
ARGOCD_BASE_URL=$(oc get route argocd-server -n openshift-gitops --template='https://{{ .spec.host }}')
ARGOCD_ADMIN_USERNAME=admin
ARGOCD_ADMIN_PASSWORD=$(oc get secret argocd-cluster -n openshift-gitops --template='{{index .data "admin.password"}}' | base64 -d)
ARGOCD_API_TOKEN=$(curl -k -s $ARGOCD_BASE_URL/api/v1/session \
  -H 'Content-Type:application/json' \
  -d '{"username":"'"$ARGOCD_ADMIN_USERNAME"'","password":"'"$ARGOCD_ADMIN_PASSWORD"'"}' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')

# Test if the params are working directly to the ArgoCD API
curl -sk $ARGOCD_BASE_URL/api/v1/applications -H "Authorization: Bearer $ARGOCD_API_TOKEN" | jq '.items[].metadata.name' 

echo "Print variables:"
echo "ARGOCD_BASE_URL: $ARGOCD_BASE_URL"
echo "ARGOCD_ADMIN_USERNAME: $ARGOCD_ADMIN_USERNAME"
echo "ARGOCD_ADMIN_PASSWORD: ${ARGOCD_ADMIN_PASSWORD:0:10}..."
echo "ARGOCD_API_TOKEN: ${ARGOCD_API_TOKEN:0:10}..."

export ARGOCD_BASE_URL=$ARGOCD_BASE_URL
export ARGOCD_API_TOKEN=$ARGOCD_API_TOKEN

TOOLGROUPS_DENYLIST='["builtin::websearch"]' gradio main.py # , "builtin::rag"
```

### Run with Podman

1. **Build the image:**
   ```bash
   podman build -t quay.io/alopezme/intelligent-cd-gradio:latest intelligent-cd-app
   ```

2. **Run the container:**
   ```bash
   podman run --network host quay.io/alopezme/intelligent-cd-gradio:latest
   ```

3. **Access the UI:**
   Open http://localhost:7860/?__theme=light

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
