# Google Cloud console URL templates

Copy-paste safe deep links for module READMEs. Always include `?project=<project>`;
region-scoped resources use the `;region=<region>` matrix segment. Use trigger ids
for Cloud Build links (names can repeat across regions); service, job and instance
names are stable.

| Resource | Template |
|---|---|
| Build history (region) | `https://console.cloud.google.com/cloud-build/builds;region=<region>?project=<project>` |
| Cloud Build trigger | `https://console.cloud.google.com/cloud-build/triggers;region=<region>/edit/<trigger_id>?project=<project>` |
| Builds filtered by trigger ids | `https://console.cloud.google.com/cloud-build/builds;region=<region>?project=<project>&query=trigger_id%3A%28<id1>%20OR%20<id2>%29` |
| Repository connections (2nd gen) | `https://console.cloud.google.com/cloud-build/repositories/2nd-gen?project=<project>` |
| Cloud Run service | `https://console.cloud.google.com/run/detail/<region>/<service>/metrics?project=<project>` |
| Cloud Run job | `https://console.cloud.google.com/run/jobs/details/<region>/<job>/executions?project=<project>` |
| Artifact Registry repo | `https://console.cloud.google.com/artifacts/docker/<project>/<region>/<repo>?project=<project>` |
| Cloud SQL instance | `https://console.cloud.google.com/sql/instances/<instance>/overview?project=<project>` |
| Cloud SQL databases | `https://console.cloud.google.com/sql/instances/<instance>/databases?project=<project>` |
| Cloud SQL users | `https://console.cloud.google.com/sql/instances/<instance>/users?project=<project>` |
| Cloud SQL operations | `https://console.cloud.google.com/sql/instances/<instance>/operations?project=<project>` |
| Memorystore Redis | `https://console.cloud.google.com/memorystore/redis/locations/<region>/instances/<instance>/details/overview?project=<project>` |
| BigQuery dataset | `https://console.cloud.google.com/bigquery?project=<project>&ws=!1m4!1m3!3m2!1s<project>!2s<dataset>` |
| Cloud Tasks queue | `https://console.cloud.google.com/cloudtasks/queue/<region>/<queue>/tasks?project=<project>` |
| VPC network | `https://console.cloud.google.com/networking/networks/details/<network>?project=<project>` |
| Cloud NAT | `https://console.cloud.google.com/net-services/nat/list?project=<project>` |
| Firewall policies | `https://console.cloud.google.com/net-security/firewall-manager/firewall-policies?project=<project>` |
| Load balancers | `https://console.cloud.google.com/net-services/loadbalancing/list/loadBalancers?project=<project>` |
| IAP | `https://console.cloud.google.com/security/iap?project=<project>` |
| Cloud DNS zones | `https://console.cloud.google.com/net-services/dns/zones?project=<project>` |
| Service account | `https://console.cloud.google.com/iam-admin/serviceaccounts/details/<sa-email>?project=<project>` |
| Secret Manager (filtered) | `https://console.cloud.google.com/security/secret-manager?project=<project>&query=<query>` |
| One secret | `https://console.cloud.google.com/security/secret-manager/secret/<secret>/versions?project=<project>` |
| Cloud Run service logs | `https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_revision%22%20resource.labels.service_name%3D%22<service>%22?project=<project>` |
| Cloud Run job logs | `https://console.cloud.google.com/logs/query;query=resource.type%3D%22cloud_run_job%22%20resource.labels.job_name%3D%22<job>%22?project=<project>` |
| Billing reports | `https://console.cloud.google.com/billing/<billing-account-id>/reports?project=<project>` |

Example for a service `api` in `my-project-dev`, region `europe-west1`:

```
https://console.cloud.google.com/run/detail/europe-west1/api/metrics?project=my-project-dev
```
