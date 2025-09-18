#!/bin/bash
set -e

echo "🚀 Starting Intelligent CD deployment..."

#####################################
# Step 1: Retrieve environment variables
#####################################

echo "📋 Step 1: Setting up environment variables..."

if [ -f .env ]; then
  source .env
else
  echo "❌ .env file not found! Please create and define required environment variables in a .env file before running this script."
  exit 1
fi

echo "✅ Environment variables configured"

#####################################
# Step 2: Calculate variables
#####################################

echo "🔐 Step 2: Retrieving ArgoCD API token..."

ARGOCD_BASE_URL=$(oc get route argocd-server -n openshift-gitops --template='https://{{ .spec.host }}')
ARGOCD_ADMIN_USERNAME=admin
ARGOCD_ADMIN_PASSWORD=$(oc get secret argocd-cluster -n openshift-gitops --template='{{index .data "admin.password"}}' | base64 -d)
ARGOCD_API_TOKEN=$(curl -k -s $ARGOCD_BASE_URL/api/v1/session \
  -H 'Content-Type:application/json' \
  -d '{"username":"'"$ARGOCD_ADMIN_USERNAME"'","password":"'"$ARGOCD_ADMIN_PASSWORD"'"}' | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')

echo "✅ ArgoCD API token retrieved successfully"

#####################################
# Step 3: Print environment variables
#####################################

echo "📊 Step 3: Environment Variables Summary:"
echo ""
echo "🤖 OLS Configuration:"
echo "  Model: $MODEL_NAME"
echo "  URL: $MODEL_API_URL"
echo "  Token: ${MODEL_API_TOKEN:0:10}..."
echo ""
echo "🚀 ArgoCD Configuration:"
echo "  Base URL: $ARGOCD_BASE_URL"
echo "  Username: $ARGOCD_ADMIN_USERNAME"
echo "  Password: ${ARGOCD_ADMIN_PASSWORD:0:10}..."
echo "  API Token: ${ARGOCD_API_TOKEN:0:10}..."
echo ""
echo "🔧 ServiceNow MCP Server Configuration:"
echo "  Instance URL: $SERVICENOW_INSTANCE_URL"
echo "  Auth Type: $SERVICENOW_AUTH_TYPE"
echo "  Username: $SERVICENOW_USERNAME"
echo "  Password: ${SERVICENOW_PASSWORD:0:3}..."
echo "  Tool Package: ${SERVICENOW_MCP_TOOL_PACKAGE}"
echo ""
echo "🔧 GitHub MCP Server Configuration:"
echo "  Auth Token: ${GITHUB_MCP_SERVER_AUTH_TOKEN:0:10}..."
echo "  Toolsets: $GITHUB_MCP_SERVER_TOOLSETS"
echo "  Readonly: $GITHUB_MCP_SERVER_READONLY"
echo ""
echo "🔧 GitLab GitOps Configuration:"
echo "  GitLab PAT: ${GITLAB_PAT:0:10}..."
echo ""
echo " Web Search using Tavily"
echo "🔧 Tavily API Token: $TAVILY_SEARCH_API_KEY"
echo ""

# Check if the GitLab GitOps secret exists in the specified namespace
if ! oc get secret gitlab-creds -n openshift-gitops &>/dev/null; then
    echo "🔐 Creating GitLab GitOps Secret..."
    
    cat <<EOF | oc apply -f -
kind: Secret
apiVersion: v1
metadata:
  name: gitlab-creds
  namespace: openshift-gitops
  labels:
    argocd.argoproj.io/secret-type: repo-creds
stringData:
  password: $GITLAB_PAT
  project: default
  type: git
  url: https://gitlab.consulting.redhat.com/rh126-demojam/intelligent-cd-iberia.git
  username: ""
  name: "GitLab GitOps Credentials"
type: Opaque
EOF
    echo "✅ GitLab GitOps Secret created successfully"
else
    echo "✅ GitLab GitOps Secret already exists. Skipping creation."
fi


#####################################
# Step 4: Create the MinIO storage
#####################################

echo "📡 Step 4: Creating MinIO storage..."
cat application-minio.yaml | \
  CLUSTER_DOMAIN=$(oc get dns.config/cluster -o jsonpath='{.spec.baseDomain}') \
  envsubst | oc apply -f -
sleep 5

echo "Waiting for MinIO pods to be ready..."

while [[ $(oc get pods -l app=minio -n minio -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do 
    echo -n "⏳" && sleep 1
done

echo "✅ MinIO pods are ready!"


#####################################
# Step 5: Create the Distributed Tracing Deployment
#####################################

echo "📡 Step 5: Configuring Distributed Tracing Stack..."
oc apply -f application-ocp-dist-tracing.yaml
sleep 5



#####################################
# Step 5: Apply the Helm Chart
#####################################

echo "🚀 Step 5: Deploying Intelligent CD application..."

helm template intelligent-cd-chart \
--set inference.model="$MODEL_NAME" \
--set inference.url="$MODEL_API_URL" \
--set inference.apiToken="$MODEL_API_TOKEN" \
--set gradioUI.env.ARGOCD_BASE_URL="https://argocd-server.openshift-gitops:443" \
--set gradioUI.env.ARGOCD_API_TOKEN="$ARGOCD_API_TOKEN" \
--set gradioUI.env.GITHUB_MCP_SERVER_AUTH_TOKEN="$GITHUB_MCP_SERVER_AUTH_TOKEN" \
--set gradioUI.env.GITHUB_MCP_SERVER_TOOLSETS='$GITHUB_MCP_SERVER_TOOLSETS' \
--set gradioUI.env.GITHUB_MCP_SERVER_READONLY="$GITHUB_MCP_SERVER_READONLY" \
--set mcpServers.servicenowMcp.env.SERVICENOW_INSTANCE_URL="$SERVICENOW_INSTANCE_URL" \
--set mcpServers.servicenowMcp.env.SERVICENOW_AUTH_TYPE="$SERVICENOW_AUTH_TYPE" \
--set mcpServers.servicenowMcp.env.SERVICENOW_USERNAME="$SERVICENOW_USERNAME" \
--set mcpServers.servicenowMcp.env.SERVICENOW_PASSWORD="$SERVICENOW_PASSWORD" \
--set mcpServers.servicenowMcp.env.MCP_TOOL_PACKAGE="$SERVICENOW_MCP_TOOL_PACKAGE" \
--set llamaStack.websearch.tavilyApiKey="$TAVILY_SEARCH_API_KEY" \
| oc apply -f -


echo "✅ Helm template applied successfully"


#####################################
# Step 6: Wait for pods to be ready
#####################################

echo "⏳ Step 6: Waiting for operator pods to be ready..."

while [[ $(oc get pods -l app=llama-stack -n intelligent-cd -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do 
    echo -n "⏳" && sleep 1
done

echo "✅ All pods are ready!"


#####################################
# Step 7: Deploy the LLS Playground
#####################################

echo "🗄️ Step 7: Deploying the LLS Playground..."

cat application-lls-playground.yaml | \
  CLUSTER_DOMAIN=$(oc get dns.config/cluster -o jsonpath='{.spec.baseDomain}') \
  LLS_ENDPOINT="http://llama-stack-service.intelligent-cd.svc.cluster.local:8321" \
  envsubst | oc apply -f -

#####################################
# Step 8: Run the pipeline
#####################################

echo "🗄️ Step 8: Populating the vector database..."

export KUBEFLOW_ENDPOINT=$(oc get route ds-pipeline-dspa -n intelligent-cd-pipelines --template="https://{{.spec.host}}")
export BEARER_TOKEN=$(oc whoami --show-token)
python intelligent-cd-pipelines/ingest-pipeline.py

echo "🎉 Installation Complete!"
echo "✨ Intelligent CD has been successfully deployed and configured!"