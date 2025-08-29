# Intelligent CD Helm Chart

This Helm chart deploys the Intelligent CD application with configurable tool access controls.

## Quick Start

```bash
helm template intelligent-cd-chart \
--set inference.model="$OLS_PROVIDER_MODEL_NAME"
--set inference.url=$OLS_PROVIDER_API_URL \
--set inference.apiToken=$OLS_PROVIDER_API_TOKEN \
--set gradioUI.env.ARGOCD_BASE_URL=https://argocd-server.openshift-gitops:443 \
--set gradioUI.env.ARGOCD_API_TOKEN=$ARGOCD_API_TOKEN \
| oc apply -f -
```

## Debug Mode
Enable debug logging:
```yaml
gradioUI:
  env:
    LOG_LEVEL: "DEBUG"
```
