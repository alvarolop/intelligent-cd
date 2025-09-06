# Intelligent CD

This project provides an application that can be deployed to an OpenShift cluster to provide a chat interface to modernize and optimize your cluster using a chat interface.

![Chatbot Interface](docs/images/chatbot.png)

## Features

- Chat interface to modernize and optimize your cluster based on **Gradio**.
- Use of **MCP servers** to provide tools to interact with OpenShift, ArgoCD, and GitHub.
- Use of **llama-stack** to coordinate all the AI components.
- Use of **Red Hat OpenShift AI** as the base platform for all the AI components.


## Architecture

The following diagram shows the architecture of the Intelligent CD application.

![Intelligent CD Architecture](docs/images/architecture.svg)



## Repository structure

This repository is organized as follows:

1. `ìntelligent-cd-app`: This is the Gradio application that provides the chat interface.
2. `intelligent-cd-chart`: This is the Helm chart that deploys the Intelligent CD application.

In order to deploy the Intelligent CD application, without customizing it, you can use the ArgoCD application `app-intelligent-cd.yaml` that is provided in this repository.




## Step 1: How to deploy

All the components can deployed using **ArgoCD**, but as there are several variables to be set, we provide a script that will set the variables and deploy the application. First, you need to create a `.env` file with the following variables:

```bash
# Model Configuration
# MODEL_NAME=llama-4-scout-17b-16e-w4a16
MODEL_API_URL=https://your-model-api-url
MODEL_API_TOKEN=your-model-api-token

# GitHub MCP Server Configuration
GITHUB_MCP_SERVER_AUTH_TOKEN="your-gh-pat-token"
GITHUB_MCP_SERVER_TOOLSETS="pull_requests, repos, issues"
GITHUB_MCP_SERVER_READONLY="true"

# ServiceNow Configuration
SERVICENOW_INSTANCE_URL=https://your-servicenow-instance-url
SERVICENOW_AUTH_TYPE=basic
SERVICENOW_USERNAME=your-servicenow-username
SERVICENOW_PASSWORD=your-servicenow-password
SERVICENOW_TOOL_PACKAGE=service_desk
```

Then, you can run the script to deploy the application:

```bash
./auto-install.sh
```

> [!CAUTION]
> **Bug: Llamastack in several namespaces**
> There is a bug in the current implementation of the Llama Stack operator provided in OpenShift AI. With this bug, the CRD that allows to deploy the Llama Stack Distribution with extra privileges is only created automatically in the first namespace where a Llama Stack Distribution is deployed.
> If you already deployed the Llama Stack Distribution in a namespace, you can create the CRD manually in the other namespaces by running the following command:
> ```bash
> oc adm policy add-cluster-role-to-user system:openshift:scc:anyuid -z llama-stack-sa --rolebinding-name llama-stack-crb-$NAMESPACE -n $NAMESPACE
> ```


### How to customize

You can customize the Intelligent CD application by modifying the `intelligent-cd-chart` Helm chart. Most of its customization is done in the `values.yaml` file that can be provided as a field of the ArgoCD application.



## Step 2: How to access the chat interface

You can use the chat interface to modernize and optimize your cluster.

You can find the chat interface at:

```bash
oc get route gradio -n intelligent-cd --template='https://{{ .spec.host }}/?__theme=light'
```

## Step 3: Ingest documents into the vector database

You can ingest documents into the vector database by running the following command:

```bash
export KUBEFLOW_ENDPOINT=$(oc get route ds-pipeline-dspa -n intelligent-cd-pipelines --template="https://{{.spec.host}}")
export BEARER_TOKEN=$(oc whoami --show-token)
python intelligent-cd-pipelines/ingest-pipeline.py
```




## Extra: Generate Intelligent CD Application Container Image

```bash
podman build -t quay.io/alopezme/intelligent-cd-gradio:latest intelligent-cd-app
podman push quay.io/alopezme/intelligent-cd-gradio:latest
```

Test the image locally:

```bash
podman run --network host quay.io/alopezme/intelligent-cd-gradio:latest
```




## GitHub MCP Server

For the GitHub MCP Server, you need to create a personal access token with the following permissions:

**Token Details:**
- Name: `github-mcp-server`
- Expires: Tuesday, September 01, 2026
- Repositories: 2 (intelligent-cd, intelligent-cd-gitops)
- Total Permissions: 14

**Required Permissions:**

| Permission | Access Level |
|------------|--------------|
| Actions | Read-only |
| Variables | Read-only |
| Administration | Read-only |
| Contents | Read-only |
| Environments | Read-only |
| Issues | Read-only |
| Merge queues | Read-only |
| Metadata | Read-only |
| Pages | Read-only |
| Pull requests | Read-only |
| Webhooks | Read-only |
| Secrets | Read-only |
| Commit statuses | Read-only |
| Workflows | Read and write |



## ServiceNow MCP Server

For the ServiceNow MCP Server, you need to create a developer instance of the ServiceNow platform:

1. Access the [Developer portal](https://developer.servicenow.com) in ServiceNow.
2. Create a new instance and access the [Management Console](https://developer.servicenow.com/dev.do#!/manage-instance).
3. Retrieve the `Instance URL`, `Username`, and `Password` from the Management Console.
4. Add those variables to the `.env` file.


