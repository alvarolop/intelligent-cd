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

All the components are deployed using **ArgoCD**. You can find the application in the `app-intelligent-cd.yaml` file.

```bash
oc apply -f app-intelligent-cd.yaml
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



### Manual deployment without ArgoCD

```bash
helm template intelligent-cd-chart \
--set inference.model="$OLS_PROVIDER_MODEL_NAME" \
--set inference.url="$OLS_PROVIDER_API_URL" \
--set inference.apiToken="$OLS_PROVIDER_API_TOKEN" \
--set gradioUI.env.ARGOCD_BASE_URL="https://argocd-server.openshift-gitops:443" \
--set gradioUI.env.ARGOCD_API_TOKEN="$ARGOCD_API_TOKEN" \
| oc apply -f -
```

## Step 2: How to access the chat interface

You can use the chat interface to modernize and optimize your cluster.

You can find the chat interface at:

```bash
oc get route gradio -n intelligent-cd --template='https://{{ .spec.host }}/?__theme=light'
```

## Step 3: Ingest documents into the vector database


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
