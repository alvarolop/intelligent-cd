# Intelligent CD

This project provides an application that can be deployed to an OpenShift cluster to provide a chat interface to modernize and optimize your cluster using a chat interface.

![Chatbot Interface](docs/images/chatbot.png)

## Features

- Chat interface to modernize and optimize your cluster based on **Gradio**.
- Use of **MCP servers** to provide tools to interact with OpenShift, ArgoCD, and GitHub.
- Use of **llama-stack** to coordinate all the AI components.
- Use of **Red Hat OpenShift AI** as the base platform for all the AI components.


## Architecture

WIP


## Bug: Llamastack in several namespaces

There is a bug in the current implementation of the Llama Stack operator provided in OpenShift AI. With this bug, the CRD that allows to deploy the Llama Stack Distribution with extra privileges is only created automatically in the first namespace where a Llama Stack Distribution is deployed.

If you already deployed the Llama Stack Distribution in a namespace, you can create the CRD manually in the other namespaces by running the following command:

```bash
oc adm policy add-cluster-role-to-user system:openshift:scc:anyuid -z llama-stack-sa --rolebinding-name llama-stack-crb-$NAMESPACE -n $NAMESPACE
```


## How to deploy

All the components are deployed using **ArgoCD**. You can find the application in the `app-intelligent-cd.yaml` file.

```bash
oc apply -f app-intelligent-cd.yaml
```

## How to use

You can use the chat interface to modernize and optimize your cluster.

You can find the chat interface at:

```bash
oc get route gradio -n intelligent-cd --template='https://{{ .spec.host }}/?__theme=light'
```


## Manual deployment

### Deploy the namespace

```bash
helm template intelligent-cd-chart \
--set inference.url=$OLS_PROVIDER_API_URL \
--set inference.apiToken=$OLS_PROVIDER_API_TOKEN \
| oc apply -f -
```

### Deploy the components
