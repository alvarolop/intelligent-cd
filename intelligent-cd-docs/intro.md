# Intelligent CD Application Deployment Guide
## OpenShift Deployment Strategy and Operational Procedures

**Document Version:** 2.1.4  
**Last Updated:** December 2024  
**Document Owner:** Platform Engineering Team  
**Contact:** platform-engineering@company.com  
**Emergency Contact:** oncall-platform@company.com (24/7)

---

## Table of Contents

1. [Introduction](#introduction)
2. [Deployment Recommendations and Constraints](#deployment-recommendations-and-constraints)
3. [Network Policies and Security](#network-policies-and-security)
4. [Routing and Load Balancing](#routing-and-load-balancing)
5. [Storage and Architecture](#storage-and-architecture)
6. [Resource Management](#resource-management)
7. [Monitoring and Observability](#monitoring-and-observability)
8. [Deployment Procedures](#deployment-procedures)
9. [Troubleshooting](#troubleshooting)
10. [Compliance and Auditing](#compliance-and-auditing)

---

## Introduction

This document outlines the deployment strategy and recommendations for the **Intelligent CD** Python-based application on OpenShift. The goal is to provide a standardized approach that ensures the application is deployed in a secure, stable, and scalable manner. These guidelines are based on OpenShift and cloud-native best practices.

### Application Overview

- **Application Name:** Intelligent CD (Intelligent Continuous Deployment)
- **Version:** 2.1.4
- **Technology Stack:** Python 3.11+, FastAPI, PostgreSQL 15, Redis 7.2
- **Deployment Target:** OpenShift 4.14+ clusters
- **Expected Load:** 1000-5000 requests/minute
- **Data Classification:** Internal Use Only (IUO)

### Key Stakeholders

| Department | Contact | Email | Phone | Responsibilities |
|------------|---------|-------|-------|------------------|
| **Platform Engineering** | Sarah Johnson | platform-engineering@company.com | +1-555-0101 | Primary deployment support |
| **Networking** | Mike Chen | networking@company.com | +1-555-0102 | Network policies, firewall rules |
| **Security** | Lisa Rodriguez | security@company.com | +1-555-0103 | Security reviews, compliance |
| **Architecture** | David Kim | architecture@company.com | +1-555-0104 | Storage design, scalability |
| **DevOps** | Alex Thompson | devops@company.com | +1-555-0105 | CI/CD pipeline, automation |
| **Database** | Maria Garcia | database@company.com | +1-555-0106 | Database provisioning, tuning |

---

## Deployment Recommendations and Constraints

Following these recommendations will help ensure the application runs smoothly within the OpenShift environment and adheres to standard security and operational practices.

### ⚠️ Security Context Constraints (SCC)

Your application must **not** require special Security Context Constraints (SCCs). The deployment should be able to run with the default `restricted` SCC. This means the application must:

- **Not run as the root user** - Must use UID 1000 or higher
- **Not require privileged access** - No CAP_SYS_ADMIN or similar capabilities
- **Not mount host paths** - Use persistent volumes instead
- **Not use host networking** - Use service networking only
- **Not require host IPC or PID namespaces**

**Approval Process for SCC Changes:**
1. Submit request to security@company.com
2. Include business justification and risk assessment
3. Security team review (2-3 business days)
4. Architecture team approval (1-2 business days)
5. Final approval from CISO office (1 business day)

**Contact for SCC Exceptions:** security@company.com with subject "SCC Exception Request - [Application Name]"

### 🧠 Resource Allocation (CPU and Memory)

Properly sizing your application is crucial for performance and cost management. You must define **resource requests and limits** for CPU and memory in your deployment configuration.

#### Resource Requirements by Environment

| Environment | CPU Request | CPU Limit | Memory Request | Memory Limit | Replicas |
|-------------|-------------|-----------|----------------|--------------|----------|
| **Development** | 100m | 200m | 128Mi | 256Mi | 1-2 |
| **Staging** | 250m | 500m | 256Mi | 512Mi | 2-3 |
| **Production** | 500m | 1000m | 512Mi | 1Gi | 3-5 |

#### Resource Configuration Example

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "1Gi"
```

**Resource Management Best Practices:**
- Set limits to 2x requests for CPU and 1.5x for memory
- Monitor resource usage with Prometheus/Grafana
- Use Horizontal Pod Autoscaler (HPA) for production workloads
- Contact database@company.com for database resource sizing

**Resource Scaling Approval:**
- **Development/Staging:** DevOps team (devops@company.com)
- **Production:** Architecture team (architecture@company.com) + CTO approval

### 🔄 Statelessness

The application must be **stateless**. This means that it should not store any session data, temporary files, or other state on its local filesystem. This is a critical requirement for a cloud-native environment.

#### Stateful Components

| Component | Storage Type | Contact | Approval Required |
|-----------|--------------|---------|-------------------|
| **User Sessions** | Redis Cluster | database@company.com | Yes - Architecture |
| **File Uploads** | S3-Compatible Storage | storage@company.com | Yes - Storage Team |
| **Application Logs** | Centralized Logging | logging@company.com | No - Standard |
| **Configuration** | ConfigMaps/Secrets | platform-engineering@company.com | No - Standard |

**Stateful Requirements Process:**
1. Submit request to architecture@company.com
2. Include storage requirements and data lifecycle
3. Architecture review (3-5 business days)
4. Storage team assessment (2-3 business days)
5. Security review for data classification (2-3 business days)

### 🪵 Logging

Your application should **write all logs to standard output (stdout) and standard error (stderr)**. OpenShift's logging system automatically collects logs from these streams.

#### Logging Standards

| Log Level | Output Stream | Retention | Contact |
|------------|---------------|-----------|---------|
| **ERROR** | stderr | 90 days | logging@company.com |
| **WARN** | stdout | 30 days | logging@company.com |
| **INFO** | stdout | 7 days | logging@company.com |
| **DEBUG** | stdout | 3 days | logging@company.com |

**Logging Configuration:**
```python
import logging
import sys

# Configure logging to stdout/stderr
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.StreamHandler(sys.stderr)
    ]
)
```

**Logging Issues Contact:** logging@company.com or oncall-platform@company.com (urgent)

### 🌐 Port Configuration

Your application should be configured to listen on port **8080**. OpenShift automatically handles routing traffic to this port.

#### Port Configuration by Service Type

| Service Type | Port | Protocol | Contact |
|--------------|------|----------|---------|
| **HTTP API** | 8080 | TCP | networking@company.com |
| **Health Check** | 8080 | TCP | platform-engineering@company.com |
| **Metrics** | 8080 | TCP | monitoring@company.com |
| **Admin Interface** | 8080 | TCP | security@company.com |

**Port Change Process:**
1. Submit request to networking@company.com
2. Include business justification and impact assessment
3. Network team review (1-2 business days)
4. Security review if non-standard port (1 business day)

### 🐳 Container Image

The application must be built into a **container image**. Use a multi-stage Dockerfile to create a small, efficient, and secure image.

#### Image Requirements

| Requirement | Specification | Contact |
|-------------|---------------|---------|
| **Base Image** | Red Hat UBI 9 minimal | security@company.com |
| **Size Limit** | < 200MB | devops@company.com |
| **Security Scan** | Passes Trivy/Clair | security@company.com |
| **Registry** | company-registry.company.com | devops@company.com |

**Image Build Process:**
1. Submit Dockerfile to devops@company.com for review
2. Security scan approval from security@company.com
3. Build and push to registry by DevOps team
4. Image signing and verification

---

## Network Policies and Security

### Network Policy Requirements

All applications must implement network policies to control pod-to-pod communication. Contact **networking@company.com** for policy creation and review.

#### Default Network Policies

| Policy Name | Purpose | Contact | Approval |
|-------------|---------|---------|----------|
| **default-deny-all** | Deny all ingress/egress | networking@company.com | Standard |
| **allow-dns** | Allow DNS resolution | networking@company.com | Standard |
| **allow-health-checks** | Allow health check traffic | networking@company.com | Standard |

#### Custom Network Policy Process

1. **Submit Request:** networking@company.com
2. **Include Details:**
   - Source and destination namespaces
   - Port and protocol requirements
   - Business justification
   - Security impact assessment
3. **Review Timeline:** 3-5 business days
4. **Implementation:** 1-2 business days after approval

#### Network Policy Example

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: intelligent-cd-network-policy
  namespace: intelligent-cd
spec:
  podSelector:
    matchLabels:
      app: intelligent-cd
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-controller
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: database
    ports:
    - protocol: TCP
      port: 5432
```

### Firewall and Security Groups

| Environment | Firewall Rules | Contact | Approval Required |
|-------------|----------------|---------|-------------------|
| **Development** | Standard rules | networking@company.com | No |
| **Staging** | Standard + monitoring | networking@company.com | No |
| **Production** | Custom rules | security@company.com | Yes - Security Team |

**Firewall Change Process:**
1. Submit to security@company.com
2. Include business justification and risk assessment
3. Security review (2-3 business days)
4. Network implementation (1 business day)

---

## Routing and Load Balancing

### Route Configuration

Contact **networking@company.com** for route creation and management.

#### Route Types

| Route Type | Purpose | Contact | Approval |
|------------|---------|---------|----------|
| **Public Route** | External access | networking@company.com | Yes - Security |
| **Internal Route** | Cluster-only access | networking@company.com | No |
| **Secure Route** | HTTPS with TLS | security@company.com | Yes - Security |

#### Route Creation Process

1. **Submit Request:** networking@company.com
2. **Required Information:**
   - Service name and namespace
   - Hostname requirements
   - TLS certificate needs
   - Access control requirements
3. **Review Timeline:** 2-3 business days
4. **Implementation:** 1 business day after approval

#### Route Configuration Example

```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: intelligent-cd-route
  namespace: intelligent-cd
spec:
  host: intelligent-cd.apps.company.com
  to:
    kind: Service
    name: intelligent-cd-service
    weight: 100
  port:
    targetPort: 8080
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

### Load Balancer Configuration

| Load Balancer Type | Use Case | Contact | Approval |
|--------------------|----------|---------|----------|
| **Application Load Balancer** | HTTP/HTTPS traffic | networking@company.com | No |
| **Network Load Balancer** | TCP/UDP traffic | networking@company.com | Yes - Architecture |
| **Classic Load Balancer** | Legacy applications | networking@company.com | Yes - Architecture |

**Load Balancer Process:**
1. Submit to networking@company.com
2. Architecture review if required (2-3 business days)
3. Implementation (3-5 business days)

---

## Storage and Architecture

### Storage Requirements

Contact **storage@company.com** for storage provisioning and management.

#### Storage Types

| Storage Type | Use Case | Contact | Approval |
|--------------|----------|---------|----------|
| **Persistent Volume (PV)** | Database storage | storage@company.com | Yes - Architecture |
| **ConfigMap** | Configuration files | platform-engineering@company.com | No |
| **Secret** | Sensitive data | security@company.com | Yes - Security |
| **EmptyDir** | Temporary storage | platform-engineering@company.com | No |

#### Storage Provisioning Process

1. **Submit Request:** storage@company.com
2. **Required Information:**
   - Storage size requirements
   - Performance requirements (IOPS, throughput)
   - Backup and retention requirements
   - Data classification
3. **Review Timeline:** 5-7 business days
4. **Provisioning:** 2-3 business days after approval

#### Storage Configuration Example

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: intelligent-cd-storage
  namespace: intelligent-cd
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
  storageClassName: fast-ssd
```

### Architecture Requirements

Contact **architecture@company.com** for architectural reviews and approvals.

#### Scalability Requirements

| Metric | Requirement | Contact | Approval |
|--------|-------------|---------|----------|
| **Horizontal Scaling** | Support 10+ replicas | architecture@company.com | Yes |
| **Vertical Scaling** | Support 4 CPU cores | architecture@company.com | Yes |
| **Database Scaling** | Support 1000+ connections | database@company.com | Yes |
| **Cache Scaling** | Support 100GB+ memory | database@company.com | Yes |

#### Architecture Review Process

1. **Submit Request:** architecture@company.com
2. **Required Documentation:**
   - System architecture diagram
   - Scalability analysis
   - Performance requirements
   - Disaster recovery plan
3. **Review Timeline:** 7-10 business days
4. **Final Approval:** Architecture Review Board

---

## Resource Management

### Resource Quotas

| Namespace | CPU Limit | Memory Limit | Storage Limit | Contact |
|-----------|-----------|--------------|---------------|---------|
| **intelligent-cd-dev** | 4 CPU | 8Gi | 100Gi | platform-engineering@company.com |
| **intelligent-cd-staging** | 8 CPU | 16Gi | 200Gi | platform-engineering@company.com |
| **intelligent-cd-prod** | 16 CPU | 32Gi | 500Gi | platform-engineering@company.com |

### Resource Monitoring

Contact **monitoring@company.com** for monitoring setup and alerts.

#### Monitoring Tools

| Tool | Purpose | Contact | Access Level |
|------|---------|---------|--------------|
| **Prometheus** | Metrics collection | monitoring@company.com | Read-only |
| **Grafana** | Dashboards | monitoring@company.com | Read-only |
| **AlertManager** | Alert routing | monitoring@company.com | Admin |
| **Thanos** | Long-term storage | monitoring@company.com | Read-only |

---

## Monitoring and Observability

### Health Check Endpoints

| Endpoint | Purpose | Response Time | Contact |
|----------|---------|---------------|---------|
| **/health** | Basic health check | < 100ms | platform-engineering@company.com |
| **/ready** | Readiness check | < 200ms | platform-engineering@company.com |
| **/live** | Liveness check | < 100ms | platform-engineering@company.com |
| **/metrics** | Prometheus metrics | < 500ms | monitoring@company.com |

### Alerting Configuration

Contact **monitoring@company.com** for alert setup and management.

#### Critical Alerts

| Alert | Severity | Response Time | Contact |
|-------|----------|---------------|---------|
| **Pod Down** | Critical | 5 minutes | oncall-platform@company.com |
| **High Memory Usage** | Warning | 15 minutes | platform-engineering@company.com |
| **High CPU Usage** | Warning | 15 minutes | platform-engineering@company.com |
| **Database Connection Failure** | Critical | 5 minutes | database@company.com |

---

## Deployment Procedures

### Pre-Deployment Checklist

1. **Security Review:** security@company.com
2. **Architecture Review:** architecture@company.com
3. **Network Policy Review:** networking@company.com
4. **Storage Review:** storage@company.com
5. **Monitoring Setup:** monitoring@company.com

### Deployment Process

1. **Submit Deployment Request:** devops@company.com
2. **Include:**
   - Application manifest files
   - Resource requirements
   - Network policies
   - Storage requirements
   - Monitoring configuration
3. **Review Timeline:** 3-5 business days
4. **Deployment:** 1-2 business days after approval

### Rollback Procedures

Contact **oncall-platform@company.com** for emergency rollbacks.

#### Rollback Triggers

| Trigger | Action | Contact | Timeline |
|---------|--------|---------|----------|
| **Critical Error** | Immediate rollback | oncall-platform@company.com | 5 minutes |
| **Performance Degradation** | Gradual rollback | platform-engineering@company.com | 30 minutes |
| **Security Issue** | Immediate rollback | security@company.com | 5 minutes |

---

## Troubleshooting

### Common Issues

| Issue | Symptoms | Solution | Contact |
|-------|----------|----------|---------|
| **Pod CrashLoopBackOff** | Pods restarting repeatedly | Check logs and resource limits | platform-engineering@company.com |
| **Network Policy Blocking** | Connection timeouts | Review network policies | networking@company.com |
| **Storage Issues** | PVC pending or failed | Check storage class and quotas | storage@company.com |
| **Route Not Working** | 404 or connection refused | Verify route configuration | networking@company.com |

### Debugging Commands

```bash
# Check pod status
oc get pods -n intelligent-cd

# Check pod logs
oc logs <pod-name> -n intelligent-cd

# Check events
oc get events -n intelligent-cd

# Check network policies
oc get networkpolicies -n intelligent-cd

# Check routes
oc get routes -n intelligent-cd
```

---

## Compliance and Auditing

### Compliance Requirements

Contact **compliance@company.com** for compliance questions and audits.

#### Required Compliance

| Compliance | Requirement | Contact | Frequency |
|------------|-------------|---------|-----------|
| **SOC 2** | Annual audit | compliance@company.com | Yearly |
| **ISO 27001** | Annual audit | compliance@company.com | Yearly |
| **GDPR** | Continuous monitoring | compliance@company.com | Monthly |
| **HIPAA** | If applicable | compliance@company.com | Quarterly |

### Audit Trail

All deployments and changes are logged and auditable. Contact **audit@company.com** for audit reports.

#### Audit Events

| Event | Logged By | Retention | Contact |
|-------|-----------|-----------|---------|
| **Deployment** | OpenShift | 7 years | audit@company.com |
| **Configuration Changes** | Git | 7 years | audit@company.com |
| **Access Changes** | LDAP | 7 years | audit@company.com |
| **Security Events** | Security tools | 7 years | security@company.com |

---

## Emergency Contacts

### 24/7 On-Call

| Team | Contact | Phone | Escalation |
|------|---------|-------|------------|
| **Platform Engineering** | oncall-platform@company.com | +1-555-9999 | DevOps Manager |
| **Security** | oncall-security@company.com | +1-555-9998 | CISO |
| **Networking** | oncall-networking@company.com | +1-555-9997 | Network Manager |
| **Database** | oncall-database@company.com | +1-555-9996 | Database Manager |

### Escalation Matrix

1. **Level 1:** On-call engineer (immediate)
2. **Level 2:** Team lead (within 30 minutes)
3. **Level 3:** Manager (within 1 hour)
4. **Level 4:** Director (within 2 hours)
5. **Level 5:** VP (within 4 hours)

---

## Document Maintenance

### Update Process

1. **Submit Changes:** platform-engineering@company.com
2. **Review:** Architecture and Security teams
3. **Approval:** Platform Engineering Manager
4. **Publication:** DevOps team

### Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 2.1.4 | Dec 2024 | Added comprehensive operational procedures | Platform Engineering |
| 2.1.3 | Nov 2024 | Updated security requirements | Security Team |
| 2.1.2 | Oct 2024 | Added monitoring guidelines | Monitoring Team |
| 2.1.1 | Sep 2024 | Initial version | Platform Engineering |

---

**For questions or updates to this document, contact:** platform-engineering@company.com

**Document ID:** INT-CD-DEPLOY-2024-001  
**Classification:** Internal Use Only (IUO)  
**Next Review Date:** March 2025
