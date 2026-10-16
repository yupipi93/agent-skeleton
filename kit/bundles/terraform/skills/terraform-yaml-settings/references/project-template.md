# YAML-driven Terraform on GCP: project template

> Large reference (about 1300 lines). Read the section you need: the section table
> is in the skill `terraform-yaml-settings`. Every name, id and domain below is a
> placeholder. The repo you work in always wins over this template.

Architectural concepts:
1. Configuration-First Approach: Infrastructure defined via YAML files
2. Workspace-Based Environments: Separate state for dev/pre/pro environments
3. Dynamic Resource Generation: Services, databases, secrets auto-created
4. Modular Design: Reusable modules with consistent patterns
5. Security by Default: Minimal privileges, encrypted secrets, private networking

## 📋 OBJECTIVE
Create scalable, maintainable, and secure GCP infrastructure using Infrastructure as Code (IaC) 
principles with environment-specific configurations and automated resource generation.

## 🏗️ PROJECT STRUCTURE
```
platform-iac/
├── settings/                          # 📁 Environment Configuration Hub
│   ├── default.yaml                   # 🔧 Base configuration (shared across all environments)
│   ├── dev.yaml                       # 🔬 Development environment overrides
│   ├── pre.yaml                       # 🧪 Pre-production environment overrides  
│   └── pro.yaml                       # 🚀 Production environment overrides
├── secrets/                           # 🔐 SOPS-encrypted secrets per env/service
│   └── {env}/{service}.enc.yaml
├── docs/                              # 📚 Structured documentation
│   ├── README.md                      #   Master index
│   ├── architecture/                  #   Current infrastructure state
│   ├── guides/                        #   Procedures and how-tos
│   ├── adr/                           #   Architecture Decision Records
│   ├── modules/                       #   Per-module documentation
│   ├── external/                      #   External system docs
│   └── standards/                     #   Project guidelines
├── locals.tf                          # 🔄 Configuration loader and local variables
├── versions.tf                        # 📌 Terraform and provider version constraints
├── providers.tf                       # 🔌 GCP provider configuration
├── project.<resource>.tf              # 🏢 Project-level resources (APIs, networking, security)
├── app.<resource>.tf                  # 📱 Application resources (Cloud Run, secrets, builds)
└── README.md                          # 📚 Project documentation
```

## 📝 CONFIGURATION FILES EXPLAINED

### 1. YAML Configuration Architecture

The YAML-driven approach separates infrastructure configuration from Terraform code,
enabling non-technical teams to modify deployments without touching HCL files.

#### settings/default.yaml - 🔧 Base Configuration (Shared Foundation)
```yaml
# ===================================================================
# BASE CONFIGURATION - SHARED ACROSS ALL ENVIRONMENTS
# ===================================================================
# This file contains settings that remain consistent across dev/pre/pro
# Environment-specific files (dev.yaml, pre.yaml, pro.yaml) override these values

# PROJECT SYSTEM CONFIGURATION
# Used for resources that need to exist before main project (e.g., Terraform state bucket)
project_sys:
  id: "your-project-sys-id"            # GCP Project for infrastructure management
  name: "your-project-sys-name"        # Human-readable system project name  
  number: "<project-number>"               # GCP Project Number (for service account references)

# GEOGRAPHIC CONFIGURATION
region_name: europe-west1              # Primary GCP region for all resources
zones_name:                            # Specific zones for multi-AZ deployments
  - europe-west1-b                     # Primary zone
  - europe-west1-c                     # Secondary zone (for HA configurations)

# CLIENT/PROJECT IDENTIFICATION
client:
  name: "prj"                          # Project abbreviation (max 3 letters, used in resource naming)
                                       # Example: "prj" becomes prefix for "prj-dev-app-name"

# INFRASTRUCTURE AS CODE METADATA  
iac: 
  repo: "your-project-iac"             # Repository name for infrastructure code (used in monitoring)

# GOOGLE CLOUD APIs ACTIVATION
# APIs are automatically enabled when infrastructure is deployed
active-apis:
  # 🏗️ Core Infrastructure APIs
  - "compute.googleapis.com"           # Compute Engine, VPCs, Load Balancers
  - "cloudresourcemanager.googleapis.com"  # Project and resource management
  - "iam.googleapis.com"               # Identity and Access Management
  - "servicenetworking.googleapis.com" # VPC peering for managed services
  - "vpcaccess.googleapis.com"         # VPC connectors for serverless

  # 🚀 Container and Build Services  
  - "cloudbuild.googleapis.com"        # CI/CD pipeline automation
  - "run.googleapis.com"               # Cloud Run serverless containers
  - "artifactregistry.googleapis.com"  # Container image storage
  
  # 💾 Storage and Database Services
  - "storage.googleapis.com"           # Cloud Storage buckets
  - "sqladmin.googleapis.com"          # Cloud SQL databases
  - "redis.googleapis.com"             # Managed Redis instances
  
  # 🤖 AI and Machine Learning (optional, add as needed)
  - "aiplatform.googleapis.com"        # Vertex AI platform
  - "texttospeech.googleapis.com"      # Text-to-Speech API
  - "speech.googleapis.com"            # Speech-to-Text API
  - "vision.googleapis.com"            # Vision AI API
  
  # 🔐 Security and Secrets Management
  - "secretmanager.googleapis.com"     # Centralized secrets storage
  - "iap.googleapis.com"               # Identity-Aware Proxy for authentication
  
  # 🌐 Networking and Certificates
  - "certificatemanager.googleapis.com" # SSL certificate management
  - "dns.googleapis.com"               # Cloud DNS service
  
  # 📬 Messaging and Queuing
  - "pubsub.googleapis.com"            # Pub/Sub messaging service
  
  # 📊 Monitoring and Observability
  - "monitoring.googleapis.com"        # Cloud Monitoring and alerting
  - "logging.googleapis.com"           # Centralized logging
```

#### settings/(dev/pre/pro).yaml - 🔬🧪🚀 Environment-Specific Configuration

```yaml
# ===================================================================
# ENVIRONMENT-SPECIFIC CONFIGURATION
# ===================================================================
# This file overrides default.yaml settings for specific environments
# Each environment (dev/pre/pro) has its own configuration file

# ENVIRONMENT PROJECT CONFIGURATION
project:
  id: "your-project-{env}-id"          # Environment-specific GCP Project ID
  name: "your-project-{env}-name"      # Human-readable project name
  number: "<project-number>"               # GCP Project Number for this environment

# SOURCE CODE REPOSITORY CONFIGURATION
git_owner: "your-org"                # Organisation or workspace on your git host (CI/CD)

# ===================================================================
# LOAD BALANCER CONFIGURATION  
# ===================================================================
# Global HTTPS Load Balancer with automatic SSL certificate management
lb:
  domain:
    - example.com                  # Primary domain for SSL certificate
    - api.example.com              # Additional domains (optional)
  timeout_sec: 30                      # Backend timeout (increase for long-running operations)

# ===================================================================
# APPLICATION SERVICES CONFIGURATION
# ===================================================================
# Each service defined here automatically receives:
# - Cloud Run deployment with dedicated service account
# - PostgreSQL database and database user  
# - Secret Manager secrets (environment variables and file volumes)
# - Load balancer backend and routing (if paths specified)
# - Cloud Build CI/CD pipeline
# - IAM permissions and security policies

app:
  # FRONTEND APPLICATION EXAMPLE
  frontend:
    name: "frontend"                   # Service identifier (used for all resource naming)
    
    # LOAD BALANCER ROUTING CONFIGURATION
    loadbalancer:
      paths: ["/*", "/app/*"]          # URL patterns that route to this service
                                       # Supports wildcards and path-based routing
    
    # CI/CD PIPELINE CONFIGURATION
    cloudbuild:
      repo_name: "your-frontend-repo"  # Repository name on your git host (must match exactly)
                                       # Note: the Cloud Build repository connection depends on this name
      inline: true                     # true = inline build steps, false = use cloudbuild.yaml file
      cloudbuild_file_path: "cloudbuild.yaml"    # Path to build config (if inline: false)
      dockerfile_path: "client/Dockerfile"       # Path to Dockerfile in repository
      build_context_path: "./client"             # Build context directory
    
    # CLOUD RUN DEPLOYMENT CONFIGURATION
    cloudrun:
      # TRAFFIC AND ACCESS CONTROL
      allow_unauthenticated: true      # Allow public access (alternative: use IAP)
      ingress: "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"  # Traffic source restrictions:
                                       # - INGRESS_TRAFFIC_ALL: Accept from anywhere
                                       # - INGRESS_TRAFFIC_INTERNAL_ONLY: VPC only  
                                       # - INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER: LB only
      
      # SCALING CONFIGURATION
      min_instances: 0                 # Scale to zero for cost optimization
      max_instances: 2                 # Max concurrent instances (adjust per environment)
      concurrency: 100                 # Requests per instance before scaling new instance
      
      # CONTAINER CONFIGURATION  
      container_port: 3000             # Port your application listens on
      timeout: "300s"                  # Request timeout (consider file uploads, AI processing)
      cpu: 1                           # vCPU allocation (1 = 1000 millicores)
      ram: "512Mi"                     # Memory allocation (Mi = Mebibytes)
      
      # ENVIRONMENT VARIABLES (Non-sensitive configuration)
      env:
        - name: NEXT_PUBLIC_API_URL
          value: "https://api.example.com"    # Backend API endpoint
        - name: NODE_ENV  
          value: "production"                     # Runtime environment
        - name: PORT
          value: "3000"                          # Application port (string format required)

  # BACKEND API EXAMPLE  
  backend:
    name: "backend"
    
    # NO LOAD BALANCER PATHS = INTERNAL SERVICE ONLY
    # This service is only accessible from within the VPC or by other services
    
    cloudbuild:
      repo_name: "your-backend-repo"
      inline: true
      dockerfile_path: "backend/Dockerfile"
      build_context_path: "./backend"
    
    cloudrun:
      allow_unauthenticated: true      # Consider setting to false for internal APIs
      ingress: "INGRESS_TRAFFIC_INTERNAL_ONLY"  # Internal VPC access only
      min_instances: 0
      max_instances: 2
      concurrency: 100
      container_port: 8000
      timeout: "300s"
      cpu: 1
      ram: "512Mi"
      
      env:
        # PATHS TO MOUNTED SECRET FILES
        - name: GOOGLE_ANALYTICS_CREDENTIALS_PATH
          value: /etc/secrets/google-analytics-credentials  # File mount path
        - name: FIREBASE_CREDENTIALS_PATH  
          value: /etc/secrets/firebase-credentials          # File mount path
        - name: DATABASE_HOST
          value: "10.20.0.3"             # Private IP from VPC (Cloud SQL)
        - name: REDIS_HOST
          value: "10.20.1.3"             # Private IP from VPC (Redis)
      
      # SECRET ENVIRONMENT VARIABLES (Hybrid: secret_env + sops_env)
      # secret_env: explicit list. sops_env: true (default) auto-discovers from
      # secrets/{env}/{service-name}.enc.yaml when file exists.
      secret_env:
        - name: OPENAI_API_KEY           # Secret name (gets prefixed: "{client}-{service}-openai-api-key")
          var_name: OPENAI_API_KEY       # Environment variable name in container
          version: latest                # Secret version to use
          # create_secret: true (default) # Terraform creates secret with placeholder
          # custom_name: false (default)     # Apply automatic naming prefix
      
      # SECRET VOLUME MOUNTS (Files mounted in container filesystem)
      secret_volume:
        - name: "google-analytics-credentials"    # Secret name (gets prefixed automatically)
          file_name: "credentials.json"          # Filename in mounted volume
          version: latest                        # Secret version to use
          mount_path: "/etc/secrets/google-analytics-credentials"  # Container mount path
        - name: "firebase-credentials" 
          file_name: "credentials.json"
          version: latest
          mount_path: "/etc/secrets/firebase-credentials"
      
      # CLOUD STORAGE VOLUME MOUNTS (Persistent storage)
      gcs_volume:
        - name: "data"                   # Volume identifier
          mount_path: "/app/data"        # Container mount path
          create_gcs: true               # Automatically create Cloud Storage bucket
          read_only: false               # Mount as read-write

# ===================================================================
# CLOUD STORAGE BUCKETS CONFIGURATION  
# ===================================================================
# Buckets for application data, assets, processing, and backups
# Each bucket includes lifecycle policies, versioning, and IAM permissions

bucket:
  # MAIN APPLICATION DATA BUCKET
  app-data:
    name: "app-data"                   # Bucket identifier (becomes: {client}-{env}-app-data)
    class: "REGIONAL"                  # Storage class options:
                                       # - STANDARD: Frequently accessed data
                                       # - NEARLINE: Monthly access, 30-day minimum
                                       # - COLDLINE: Quarterly access, 90-day minimum  
                                       # - ARCHIVE: Annual access, 365-day minimum
    uniform_access: true               # Uniform bucket-level access (recommended for security)
    enable_versioning: true            # Keep object versions for recovery and audit
    soft_delete_days: 7                # Retention period for deleted objects (7-90 days)
    force_destroy: false               # Protect against accidental bucket deletion
    
    # LIFECYCLE MANAGEMENT RULES
    lifecycle_rules:
      delete_temp_files:               # Rule identifier
        age: 30                        # Apply rule after 30 days
        action_type: "Delete"          # Action: Delete, SetStorageClass, or AbortIncompleteMultipartUpload
        prefixes: ["temp/", "tmp/"]    # Apply only to objects with these prefixes
      archive_old_data:
        age: 365                       # After 1 year
        action_type: "SetStorageClass" # Move to cheaper storage class
        action_sc: "ARCHIVE"           # Target storage class
    
    # IAM PERMISSIONS CONFIGURATION
    permissions:
      admin:
        members: ["group:ops-team@example.com"]    # Operations team full access
        roles: ["roles/storage.admin"]             # Full bucket management
      app_access:
        # SPECIAL SYNTAX: "cloudrun:service-name" transforms to service account email
        # Example: "cloudrun:backend" → "serviceAccount:{client}-backend-sa@{project}.iam.gserviceaccount.com"
        members: ["cloudrun:backend", "cloudrun:frontend"]
        roles: ["roles/storage.objectCreator", "roles/storage.objectViewer"]
      public_read:                     # For publicly served content (optional)
        members: ["allUsers"]          # Public access
        roles: ["roles/storage.objectViewer"]

# ===================================================================
# NETWORK CONFIGURATION
# ===================================================================
# Virtual Private Cloud (VPC) setup for secure internal communication

network:
  network_tier: PREMIUM                # Network tier options:
                                       # - PREMIUM: Google's high-performance network
                                       # - STANDARD: Regional internet connectivity
  internal_connection: true            # Create VPC connector for serverless services
  services_cidr: "10.10.1.0/24"       # IP range for services subnet (254 usable IPs)
                                       # Common private ranges: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
  private_google_access: true          # Allow access to Google APIs without external IP

# ===================================================================
# DATABASE CONFIGURATION (OPTIONAL)
# ===================================================================
# Shared PostgreSQL instance with automatic database and user creation per service

sql:
  version: "POSTGRES_15"               # Database version (POSTGRES_13, POSTGRES_14, POSTGRES_15)
  tier: "db-f1-micro"                  # Machine type options:
                                       # - db-f1-micro: 1 vCPU, 0.6GB RAM (dev/test)
                                       # - db-g1-small: 1 vCPU, 1.7GB RAM  
                                       # - db-n1-standard-1: 1 vCPU, 3.75GB RAM (production)
  availability: "ZONAL"                # Availability options:
                                       # - ZONAL: Single zone (cheaper, no HA)
                                       # - REGIONAL: Multi-zone HA (higher cost, better reliability)
  ipv4_enabled: true                   # Allow external IP (set false for private-only)
  ssl_mode: "ENCRYPTED_ONLY"           # SSL enforcement options:
                                       # - ALLOW_UNENCRYPTED_AND_ENCRYPTED: Both allowed
                                       # - ENCRYPTED_ONLY: Require SSL (recommended)
                                       # - TRUSTED_CLIENT_CERTIFICATE_REQUIRED: Client cert required
  binary_log_enabled: true             # Enable transaction logs for point-in-time recovery
  
  # STORAGE CONFIGURATION
  disk:
    type: "PD_SSD"                     # Disk type: PD_HDD (cheaper) or PD_SSD (faster)
    size: 10                           # Storage size in GB (minimum 10GB)
  
  replica: 0                           # Number of read replicas (0 for cost savings in dev/pre)
  deletion_protection: true            # Prevent accidental database deletion
  
  # DATABASE PERFORMANCE TUNING
  flags:
    max_connections: 200               # Maximum concurrent connections
    shared_preload_libraries: "pg_stat_statements"  # Enable query statistics
    log_statement: "all"               # Log all SQL statements (adjust for production)
  
  # AUTOMATED BACKUP CONFIGURATION
  backup:
    start_time: "02:00"                # Daily backup time (UTC, during low usage)
    retained_backups: 7                # Number of backups to retain
    location: "eu"                     # Backup storage region
  
  # MAINTENANCE WINDOW (When updates can be applied)
  maintenance:
    day: 7                             # Day of week (1=Monday, 7=Sunday)  
    hour: 3                            # Hour of day (UTC)

# ===================================================================
# MONITORING AND ALERTING CONFIGURATION
# ===================================================================
# Comprehensive monitoring for applications and infrastructure

monitoring:
  # CLOUD RUN SERVICE MONITORING
  cloudrun:
    cpu:
      duration: "1800s"                # Alert if condition persists (30 minutes)
      threshold_value: 0.85            # Alert threshold (85% CPU usage)
      alignment_period: "60s"          # Data sampling interval
    memory:
      duration: "300s"                 # Alert quickly on memory issues (5 minutes)
      threshold_value: 0.95            # Alert threshold (95% memory usage)
      alignment_period: "60s"
    instances_count:
      duration: "900s"                 # Alert on scaling issues (15 minutes)
      alignment_period: "60s"
      trigger_count_series: 1          # Number of violations to trigger alert
    request_5XX_count:
      duration: "300s"                 # Alert quickly on server errors
      threshold_value: 50              # Alert if > 50 5XX errors in period
      alignment_period: "60s"
      trigger_count_series: 1

  # LOAD BALANCER MONITORING
  lb:
    request_count:
      duration: "180s"                 # Monitor traffic patterns (3 minutes)
      threshold_value: -1              # No upper limit (monitoring only)
      alignment_period: "600s"         # 10-minute data aggregation
      severity: "WARNING"              # Alert severity level
      enabled: true
    latency:
      duration: "300s"                 # Alert on slow responses (5 minutes)
      threshold_value: 3000            # Alert if latency > 3 seconds (3000ms)
      alignment_period: "60s"
      severity: "WARNING"
      enabled: true
    status_4xx_backends:
      duration: "180s"                 # Monitor client errors (3 minutes)
      threshold_value: 100             # Alert if > 100 4XX errors
      alignment_period: "60s"
      severity: "ERROR"                # Higher severity for client errors
      enabled: true
    status_5xx_backends:
      duration: "180s"                 # Monitor server errors (critical)
      threshold_value: 25              # Alert if > 25 5XX errors (low threshold)
      alignment_period: "60s"
      severity: "ERROR"                # Critical severity for server errors
      enabled: true
```

### 2. CORE TERRAFORM FILES EXPLAINED

#### locals.tf - 🔄 Configuration Loader and Variables
```hcl
# ===================================================================
# CONFIGURATION LOADER AND LOCAL VARIABLES
# ===================================================================
# This file implements the YAML-driven configuration pattern, loading
# settings from environment-specific files and merging with defaults

locals {
  # WORKSPACE-BASED CONFIGURATION LOADING
  # Terraform workspaces (dev, pre, pro) determine which YAML file to load
  workspace_file = "./settings/${terraform.workspace}.yaml"
  defaults       = file("./settings/default.yaml")
  
  # SAFE CONFIGURATION LOADING
  # Check if environment file exists, fallback to empty if not found
  workspace_data = fileexists(local.workspace_file) ? file(local.workspace_file) : yamlencode({})
  
  # CONFIGURATION MERGING
  # Environment-specific settings override defaults
  # merge() is SHALLOW: a top-level key in the env file replaces the whole
  # default block. Repeat every nested key you need, or merge per block.
  settings = merge(
    yamldecode(local.defaults),
    yamldecode(local.workspace_data)
  )
  
  # RESOURCE NAMING CONVENTIONS
  # Consistent naming across all resources for easier management
  base_name        = format("%s", local.settings.client.name)                    # "prj"
  base_name_medium = format("%s-%s", local.settings.client.name, terraform.workspace)  # "prj-dev"
  base_name_long   = format("%s-%s-%s", local.settings.client.name, terraform.workspace, "suffix")  # "prj-dev-app"
  
  # COMPUTED VALUES
  # Derive common values to avoid repetition
  region_short = replace(local.settings.region_name, "europe-west", "ew")        # "ew1" from "europe-west1"
  
  # ENVIRONMENT DETECTION
  # Conditional logic based on workspace
  is_production = terraform.workspace == "pro"
  is_development = terraform.workspace == "dev"
  
  # COMMON TAGS
  # Standardized tagging for resource management
  common_tags = {
    Environment = terraform.workspace
    Project     = local.settings.client.name
    ManagedBy   = "terraform"
    Repository  = local.settings.iac.repo
  }
}
```

#### versions.tf - 📌 Provider Versions and Backend Configuration
```hcl
# ===================================================================
# TERRAFORM AND PROVIDER VERSION CONSTRAINTS
# ===================================================================
# Pin versions for reproducible deployments and security

terraform {
  # TERRAFORM VERSION CONSTRAINT
  # Use specific version for consistency across team
  required_version = ">= 1.10.0"
  
  # REMOTE STATE BACKEND CONFIGURATION
  # Store Terraform state in Google Cloud Storage for team collaboration
  backend "gcs" {
    bucket = "your-project-tfstate"    # State storage bucket (create manually first)
    prefix = "terraform/state"         # State file path prefix
    # Optional: Enable state encryption
    # encryption_key = "your-encryption-key"
  }
  
  # PROVIDER VERSION CONSTRAINTS
  # Use pessimistic version constraints (~>) to allow patch updates only
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.42.0"           # Allow 6.42.x versions only
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.42.0"           # Beta features provider
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7.0"            # For generating random values
    }
  }
}
```

#### providers.tf - 🔌 Provider Configuration
```hcl
# ===================================================================
# GOOGLE CLOUD PROVIDER CONFIGURATION
# ===================================================================
# Configure GCP providers with authentication and default settings

# CURRENT GCP CLIENT CONFIGURATION
# Retrieve current authentication context for reference
data "google_client_config" "default" {
  provider = google
}

# GOOGLE BETA PROVIDER
# Access to beta/preview features (use sparingly in production)
provider "google-beta" {
  project = local.settings.project.id       # Target GCP project
  region  = local.settings.region_name      # Default region for resources
  
  # OPTIONAL: Additional configuration
  # zone    = local.settings.zones_name[0]   # Default zone
  # credentials = "path/to/credentials.json" # Service account key (if not using ADC)
  
  # BATCH REQUESTS (for better performance)
  batching {
    send_after      = "10s"                  # Send batch after 10 seconds
    enable_batching = true                   # Enable request batching
  }
}

# STANDARD GOOGLE PROVIDER  
# For stable/GA features (preferred for production)
provider "google" {
  project = local.settings.project.id
  region  = local.settings.region_name
  
  # USER PROJECT OVERRIDE
  # Use this project for quota and billing when accessing APIs
  user_project_override = true
  
  # BATCH REQUESTS
  batching {
    send_after      = "10s"
    enable_batching = true
  }
}
```

## 💻 TERRAFORM RESOURCE FILE EXAMPLES

### Project-Level Resources (Infrastructure Foundation)

#### project.apis.tf - 📡 Google Cloud APIs Management
```hcl
# ===================================================================
# GOOGLE CLOUD APIS ACTIVATION
# ===================================================================
# Enable required APIs for the project based on YAML configuration

# ENABLE APIS FROM CONFIGURATION
resource "google_project_service" "project_apis" {
  for_each = toset(local.settings.active-apis)
  
  project = local.settings.project.id
  service = each.value
  
  # PREVENT ACCIDENTAL API DISABLE
  disable_dependent_services = false
  disable_on_destroy         = false
  
  timeouts {
    create = "30m"    # API activation can take time
    read   = "10m"
    update = "20m"
    delete = "20m"
  }
}

# WAIT FOR ESSENTIAL APIS
# Some resources depend on specific APIs being enabled first
resource "time_sleep" "wait_for_apis" {
  depends_on = [google_project_service.project_apis]
  
  create_duration = "60s"    # Wait 60 seconds for API propagation
}
```

#### project.network.tf - 🌐 VPC and Networking Configuration  
```hcl
# ===================================================================
# VPC NETWORK AND SECURITY CONFIGURATION
# ===================================================================
# Create secure network foundation for all services

# VPC NETWORK MODULE
# Use tested, reusable networking module
module "network" {
  source = "git::https://github.com/your-org/terraform-gcp-network.git?ref=v1.0.0"

  # BASIC CONFIGURATION
  base_name          = format("%s-vpc", local.base_name)    # Network name
  gcp_project_id     = local.settings.project.id           # Target project
  gcp_project_sys_id = local.settings.project_sys.id       # System project for monitoring
  network_tier       = local.settings.network.network_tier # PREMIUM or STANDARD
  internal_connection = local.settings.network.internal_connection  # VPC connector for serverless

  # SUBNET CONFIGURATION
  # Define subnets for different resource types
  subnets = {
    services = {
      cidr                  = local.settings.network.services_cidr      # IP range for services
      region               = local.settings.region_name                # Target region
      private_google_access = local.settings.network.private_google_access  # Access Google APIs via private IP
      purpose              = null                                       # General purpose subnet
      role                 = null                                       # No special role
    }
    # ADD MORE SUBNETS AS NEEDED
    # management = {
    #   cidr   = "10.10.2.0/24"
    #   region = local.settings.region_name
    #   private_google_access = true
    # }
  }

  # PRIVATE SERVICE NETWORKING
  # For managed services like Cloud SQL
  services_ip_ranges = {
    private = {
      address       = null        # Auto-assign IP range
      prefix_length = 16          # /16 network size
      purpose       = "VPC_PEERING"
      address_type  = "INTERNAL"
    }
  }

  # METADATA FOR MONITORING
  repo_iac = local.settings.iac.repo
  
  depends_on = [time_sleep.wait_for_apis]
}

# FIREWALL RULES
# Define network security rules
resource "google_compute_firewall" "allow_internal" {
  name    = "${local.base_name}-allow-internal"
  network = module.network.network_name
  
  # ALLOW INTERNAL COMMUNICATION
  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443", "8080"]
  }
  
  source_ranges = [local.settings.network.services_cidr]  # Only internal traffic
  target_tags   = ["internal-service"]
  
  depends_on = [module.network]
}

resource "google_compute_firewall" "allow_health_checks" {
  name    = "${local.base_name}-allow-health-checks"
  network = module.network.network_name
  
  # ALLOW LOAD BALANCER HEALTH CHECKS
  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }
  
  # Google's health check IP ranges
  source_ranges = ["130.211.0.0/22", "35.191.0.0/16"]
  target_tags   = ["cloud-run"]
  
  depends_on = [module.network]
}
```

### Application-Level Resources (Services and Applications)

#### app.cloudrun.tf - 🚀 Cloud Run Service Deployment

The module source is a placeholder for your own (or a public registry) Cloud Run
module; the input shape is what matters.
```hcl
# ===================================================================
# CLOUD RUN SERVICES DEPLOYMENT
# ===================================================================
# Deploy containerized applications using standardized module

# CLOUD RUN SERVICES MODULE
# Deploys one Cloud Run service per app configuration entry
module "cloud_run_services" {
  for_each = local.settings.app    # Deploy all services defined in YAML

  source = "git::https://github.com/your-org/terraform-gcp-cloud-run.git?ref=v1.0.0"

  # SERVICE IDENTIFICATION
  base_name         = format("%s-%s", local.base_name, try(each.value.name, each.key))
  gcp_project_id    = local.settings.project.id
  gcp_project_sys_id = local.settings.project_sys.id
  region_name       = local.settings.region_name
  deletion_protection = false    # Allow deletion in non-production environments

  # SERVICE ACCOUNT CONFIGURATION
  # Each service gets dedicated service account for security isolation
  service_account = {
    name     = format("%s-%s-sa", local.base_name, try(each.value.name, each.key))
    external = false    # Create new service account (vs. using existing)
  }

  # CLOUD RUN CONFIGURATION
  cloudrun = {
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"          # Use gen2 runtime
    concurrency          = try(each.value.cloudrun.concurrency, 100)     # Requests per instance
    ingress              = try(each.value.cloudrun.ingress, "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER")
    timeout              = try(each.value.cloudrun.timeout, "300s")       # Request timeout

    # CONTAINER CONFIGURATION
    containers = [
      {
        name  = try(each.value.name, each.key)
        image = "us-docker.pkg.dev/cloudrun/container/hello:latest"    # Placeholder image
        
        # NETWORKING
        ports = {
          container_port = try(each.value.cloudrun.container_port, 8080)
        }

        # RESOURCE ALLOCATION
        resources = {
          cpu               = format("%dm", try(each.value.cloudrun.cpu, 1) * 1000)  # Convert to millicores
          memory            = try(each.value.cloudrun.ram, "512Mi")           # Memory allocation
          startup_cpu_boost = true                                            # Extra CPU during startup
          cpu_idle          = false                                           # Don't throttle CPU when idle
        }

        # ENVIRONMENT VARIABLES
        # Combine default variables with custom ones from configuration
        envs = concat([
          # DEFAULT ENVIRONMENT VARIABLES
          {
            name  = "SERVICE_NAME"
            value = try(each.value.name, each.key)
          },
          {
            name  = "REGION"  
            value = local.settings.region_name
          },
          {
            name  = "PROJECT"
            value = local.settings.project.id
          }
        ], 
        # CUSTOM ENVIRONMENT VARIABLES FROM YAML
        [
          for env_var in try(each.value.cloudrun.env, []) : {
            name  = env_var.name
            value = tostring(env_var.value)    # Ensure string type
          }
        ])

        # SECRET ENVIRONMENT VARIABLES
        # Mount secrets as environment variables
        secrets = try(each.value.cloudrun.secret_env, null) != null ? [
          for secret in each.value.cloudrun.secret_env : {
            name    = secret.var_name                                         # Env var name in container
            secret  = try(secret.create_secret, true) != false ? 
                     google_secret_manager_secret.run_secrets[try(secret.custom_name, false) ? secret.name : "${local.base_name}-${try(each.value.name, each.key)}-${secret.name}"].secret_id : 
                     (try(secret.custom_name, false) ? secret.name : "${local.base_name}-${try(each.value.name, each.key)}-${secret.name}")
            project = local.settings.project.id
            version = try(secret.version, "latest")
          }
        ] : []

        # SECRET VOLUME MOUNTS
        # Mount secrets as files in the container filesystem
        volumes = try(each.value.cloudrun.secret_volume, null) != null ? {
          for volume in each.value.cloudrun.secret_volume : volume.name => {
            mount_path = volume.mount_path
            secret = {
              secret       = try(volume.create_secret, true) != false ? 
                            google_secret_manager_secret.run_secrets[try(volume.custom_name, false) ? volume.name : "${local.base_name}-${try(each.value.name, each.key)}-${volume.name}"].secret_id : 
                            (try(volume.custom_name, false) ? volume.name : "${local.base_name}-${try(each.value.name, each.key)}-${volume.name}")
              default_mode = try(volume.default_mode, "0444")               # File permissions
              items = {
                path    = volume.file_name                                  # Filename in volume
                version = try(volume.version, "latest")                     # Secret version
              }
            }
          }
        } : {}
      }
    ]

    # VPC NETWORK ACCESS
    # Connect service to private VPC network
    vpc_access = {
      egress = "ALL_TRAFFIC"                                                # Route all traffic through VPC
      network_interfaces = {
        network    = format("%s-vpc", local.base_name)                      # Target VPC network
        subnetwork = format("%s-vpc--services", local.base_name)            # Target subnet
        tags       = ["cloud-run"]                                         # Network tags for firewall rules
      }
    }

    # AUTOSCALING CONFIGURATION
    autoscaling = {
      min = try(each.value.cloudrun.min_instances, 0)                       # Minimum instances (0 = scale to zero)
      max = try(each.value.cloudrun.max_instances, 10)                      # Maximum instances
    }
  }

  # IAM PERMISSIONS
  # Grant necessary permissions to the service
  permissions = merge({
    # CLOUD BUILD PERMISSIONS (for deployment)
    cloudbuild = {
      account     = "serviceAccount:${local.settings.project.number}@cloudbuild.gserviceaccount.com"
      permissions = ["roles/run.admin"]
    }
  }, 
  # CONDITIONAL PUBLIC ACCESS
  try(each.value.cloudrun.allow_unauthenticated, false) ? {
    cloudrun_all = {
      account     = "allUsers"
      permissions = ["roles/run.invoker"]
    }
  } : {})

  # DEPENDENCIES
  # Ensure other resources are created first
  depends_on = [
    google_secret_manager_secret_version.run_secrets_version,
    module.artifact_registry,
    module.network
  ]

  # MONITORING CONFIGURATION
  monitoring = merge(
    local.settings.monitoring.cloudrun,
    {
      notification_channels = []                    # TODO: Add notification channels
      repo_iac             = local.settings.iac.repo
    }
  )
}
```

#### app.secrets.tf - 🔐 Secret Manager Configuration
```hcl
# ===================================================================
# SECRET MANAGER CONFIGURATION
# ===================================================================
# Centralized secrets management for all services

# LOCAL VARIABLES FOR SECRET PROCESSING
locals {
  # EXTRACT ENVIRONMENT VARIABLE SECRETS
  # Process all secret_env configurations from all services
  env_secrets = flatten([
    for service_key, service_config in local.settings.app : [
      for secret in try(service_config.cloudrun.secret_env, []) : {
        # SECRET NAMING LOGIC
        key          = try(secret.custom_name, false) ? secret.name : "${local.base_name}-${service_config.name}-${secret.name}"
        service_name = service_config.name
        secret_name  = secret.name
        type         = "env"
        create_secret = try(secret.create_secret, true)        # Default: create secret
        custom_name     = try(secret.custom_name, false)            # Default: apply prefix
      } if try(secret.create_secret, true) != false            # Only create if not explicitly disabled
    ]
  ])
  
  # EXTRACT VOLUME SECRETS
  # Process all secret_volume configurations from all services
  volume_secrets = flatten([
    for service_key, service_config in local.settings.app : [
      for secret in try(service_config.cloudrun.secret_volume, []) : {
        key          = try(secret.custom_name, false) ? secret.name : "${local.base_name}-${service_config.name}-${secret.name}"
        service_name = service_config.name
        secret_name  = secret.name
        type         = "volume"
        create_secret = try(secret.create_secret, true)
        custom_name     = try(secret.custom_name, false)
      } if try(secret.create_secret, true) != false
    ]
  ])
  
  # COMBINE ALL SECRETS
  service_secrets = concat(local.env_secrets, local.volume_secrets)
  
  # CONVERT TO MAP FOR FOR_EACH
  secrets_map = { for item in local.service_secrets : item.key => item }
}

# CREATE SECRET MANAGER SECRETS
resource "google_secret_manager_secret" "run_secrets" {
  for_each = local.secrets_map

  project   = local.settings.project.id
  secret_id = each.key

  # REPLICATION CONFIGURATION
  # Store secrets in specific region for data residency
  replication {
    user_managed {
      replicas {
        location = local.settings.region_name
      }
    }
  }
  
  # LABELS FOR ORGANIZATION
  labels = {
    service     = each.value.service_name
    type        = each.value.type
    environment = terraform.workspace
    managed_by  = "terraform"
  }
}

# CREATE SECRET VERSIONS WITH PLACEHOLDER VALUES
resource "google_secret_manager_secret_version" "run_secrets_version" {
  for_each = local.secrets_map

  secret      = google_secret_manager_secret.run_secrets[each.key].id
  secret_data = "PLACEHOLDER_VALUE_TO_BE_REPLACED"    # Replace with actual values after deployment

  # LIFECYCLE MANAGEMENT
  # Allow external management of secret values
  lifecycle {
    ignore_changes = [secret_data]                    # Don't override manual updates
  }
  
  depends_on = [google_secret_manager_secret.run_secrets]
}

# GRANT SERVICE ACCOUNTS ACCESS TO SECRETS
resource "google_secret_manager_secret_iam_member" "run_secrets_access" {
  for_each = local.secrets_map

  project   = local.settings.project.id
  secret_id = google_secret_manager_secret.run_secrets[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.base_name}-${each.value.service_name}-sa@${local.settings.project.id}.iam.gserviceaccount.com"

  depends_on = [google_secret_manager_secret.run_secrets]
}
```

## ✅ COMPREHENSIVE BEST PRACTICES

### 1. 🏗️ Environment Management Strategy
```hcl
# WORKSPACE-BASED RESOURCE CREATION
# Use count or for_each with workspace conditions for environment-specific resources

# Example: Create high-availability database only in production
resource "google_sql_database_instance" "ha_database" {
  count = terraform.workspace == "pro" ? 1 : 0    # Only create in production
  
  name             = "${local.base_name}-ha-db"
  database_version = "POSTGRES_15"
  region          = local.settings.region_name
  
  settings {
    tier              = "db-n1-standard-2"        # Larger instance for production
    availability_type = "REGIONAL"                # High availability
  }
}

# ENVIRONMENT-SPECIFIC CONFIGURATIONS
# Use conditional logic for environment differences
locals {
  # INSTANCE COUNTS BY ENVIRONMENT
  instance_count = terraform.workspace == "pro" ? 3 : (terraform.workspace == "pre" ? 2 : 1)
  
  # BACKUP RETENTION BY ENVIRONMENT  
  backup_retention = terraform.workspace == "pro" ? 30 : (terraform.workspace == "pre" ? 7 : 3)
  
  # MONITORING ALERTING BY ENVIRONMENT
  enable_alerting = terraform.workspace == "pro" ? true : false
}
```

### 2. 🔐 Security Best Practices Implementation
```hcl
# SERVICE ACCOUNT WITH MINIMAL PERMISSIONS
resource "google_service_account" "app_service_account" {
  account_id   = "${local.base_name}-${var.service_name}-sa"
  display_name = "Service Account for ${var.service_name}"
  description  = "Minimal permissions for ${var.service_name} service"
}

# GRANULAR IAM BINDINGS
# Grant only necessary permissions to specific resources
resource "google_storage_bucket_iam_member" "app_bucket_access" {
  bucket = google_storage_bucket.app_bucket.name
  role   = "roles/storage.objectCreator"            # Read-write access
  member = "serviceAccount:${google_service_account.app_service_account.email}"
}

resource "google_storage_bucket_iam_member" "app_bucket_viewer" {
  bucket = google_storage_bucket.public_bucket.name  
  role   = "roles/storage.objectViewer"             # Read-only access
  member = "serviceAccount:${google_service_account.app_service_account.email}"
}

# SECRET ACCESS CONTROL
# Limit secret access to specific services
resource "google_secret_manager_secret_iam_member" "secret_access" {
  for_each = toset(var.allowed_services)
  
  secret_id = google_secret_manager_secret.app_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.base_name}-${each.value}-sa@${var.project_id}.iam.gserviceaccount.com"
}
```

### 3. 📊 Monitoring and Observability Framework
```hcl
# COMPREHENSIVE ALERTING POLICY
resource "google_monitoring_alert_policy" "service_health" {
  display_name = "${local.base_name} Service Health Monitoring"
  combiner     = "OR"                               # Trigger if any condition is met
  
  # MULTIPLE CONDITIONS FOR COMPREHENSIVE MONITORING
  conditions {
    display_name = "High Error Rate"
    
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${var.service_name}\""
      comparison      = "COMPARISON_GREATER_THAN"
      threshold_value = 0.05                        # 5% error rate threshold
      duration        = "300s"                      # Sustained for 5 minutes
      
      aggregations {
        alignment_period   = "60s"                  # 1-minute windows
        per_series_aligner = "ALIGN_RATE"          # Calculate rate of errors
      }
    }
  }
  
  conditions {
    display_name = "High Latency"
    
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${var.service_name}\""
      comparison      = "COMPARISON_GREATER_THAN" 
      threshold_value = 2000                        # 2 seconds
      duration        = "300s"
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_95"  # 95th percentile latency
      }
    }
  }
  
  # NOTIFICATION CONFIGURATION
  notification_channels = var.notification_channels
  
  # ALERT DOCUMENTATION
  documentation {
    content = "Service ${var.service_name} is experiencing issues. Check logs and service health."
    mime_type = "text/markdown"
  }
}

# LOGGING CONFIGURATION
resource "google_logging_metric" "error_rate" {
  name   = "${local.base_name}-error-rate"
  filter = "resource.type=cloud_run_revision AND resource.labels.service_name=${var.service_name} AND severity>=ERROR"
  
  metric_descriptor {
    metric_kind = "GAUGE"
    value_type  = "DOUBLE"
    display_name = "Error Rate for ${var.service_name}"
  }
  
  value_extractor = "EXTRACT(jsonPayload.error_count)"
}
```

### 4. 💾 State Management and Data Protection
```hcl
# TERRAFORM BACKEND CONFIGURATION
terraform {
  backend "gcs" {
    bucket = "your-project-tfstate"
    prefix = "terraform/state"
    
    # STATE ENCRYPTION (optional): backends cannot read variables, so pass a
    # customer-managed key with -backend-config or use kms_encryption_key.
    # kms_encryption_key = "projects/my-project-id/locations/europe/keyRings/tf/cryptoKeys/state"
    
    # STATE LOCKING
    # GCS automatically provides state locking
  }
}

# RESOURCE PROTECTION
resource "google_storage_bucket" "important_data" {
  name     = "${local.base_name}-critical-data"
  location = local.settings.region_name
  
  # PREVENT ACCIDENTAL DELETION
  lifecycle {
    prevent_destroy = true                          # Block terraform destroy
  }
  
  # VERSIONING FOR DATA PROTECTION
  versioning {
    enabled = true
  }
  
  # RETENTION POLICY
  retention_policy {
    retention_period = 2592000                      # 30 days minimum retention
    is_locked       = terraform.workspace == "pro" # Lock policy in production
  }
}

# BACKUP AUTOMATION
resource "google_storage_bucket" "backup_bucket" {
  name     = "${local.base_name}-automated-backups"
  location = local.settings.region_name
  
  # LIFECYCLE MANAGEMENT FOR COST OPTIMIZATION
  lifecycle_rule {
    condition {
      age = 90                                      # 90 days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"                    # Move to cheaper storage
    }
  }
  
  lifecycle_rule {
    condition {
      age = 365                                     # 1 year
    }
    action {
      type = "Delete"                               # Remove old backups
    }
  }
}
```

### 5. 🚀 Performance and Cost Optimization
```hcl
# CLOUD RUN OPTIMIZATION
# Shown with the v1 resource for brevity; new code should use
# google_cloud_run_v2_service (scaling under template.scaling, probes under
# template.containers.startup_probe / liveness_probe).
resource "google_cloud_run_service" "optimized_service" {
  name     = "${local.base_name}-optimized-service"
  location = local.settings.region_name
  
  template {
    spec {
      # RESOURCE OPTIMIZATION
      containers {
        # RIGHT-SIZE RESOURCES BASED ON ENVIRONMENT
        resources {
          limits = {
            cpu    = terraform.workspace == "pro" ? "2000m" : "1000m"    # More CPU in production
            memory = terraform.workspace == "pro" ? "2Gi" : "512Mi"     # More memory in production
          }
        }
        
        # STARTUP OPTIMIZATION
        startup_probe {
          http_get {
            path = "/health"
          }
          initial_delay_seconds = 10
          period_seconds       = 3
          timeout_seconds      = 1
          failure_threshold    = 3
        }
        
        # LIVENESS PROBE
        liveness_probe {
          http_get {
            path = "/health"
          }
          period_seconds    = 10
          timeout_seconds   = 1
          failure_threshold = 3
        }
      }
      
      # SCALING CONFIGURATION
      container_concurrency = 100                   # Optimize for your workload
      timeout_seconds      = 300                    # Match your SLA requirements
    }
    
    metadata {
      annotations = {
        # COST OPTIMIZATION
        "autoscaling.knative.dev/minScale" = "0"    # Scale to zero
        "autoscaling.knative.dev/maxScale" = terraform.workspace == "pro" ? "100" : "10"
        
        # PERFORMANCE OPTIMIZATION  
        "run.googleapis.com/execution-environment" = "gen2"  # Use gen2 for better performance
        "run.googleapis.com/cpu-throttling"       = "false" # Disable CPU throttling
      }
    }
  }
  
  traffic {
    percent         = 100
    latest_revision = true
  }
}

# LOAD BALANCER OPTIMIZATION
resource "google_compute_backend_service" "optimized_backend" {
  name        = "${local.base_name}-optimized-backend"
  protocol    = "HTTP"
  timeout_sec = 30
  
  # CONNECTION DRAINING
  connection_draining_timeout_sec = 30
  
  # CDN CONFIGURATION FOR STATIC CONTENT
  enable_cdn = true
  cdn_policy {
    cache_key_policy {
      include_host         = true
      include_protocol     = true
      include_query_string = false                 # Don't cache query parameters
    }
    default_ttl  = 3600                           # 1 hour default cache
    max_ttl      = 86400                          # 24 hours maximum cache
    client_ttl   = 3600                           # 1 hour client cache
  }
  
  # HEALTH CHECK OPTIMIZATION
  health_checks = [google_compute_health_check.optimized_health_check.id]
}

resource "google_compute_health_check" "optimized_health_check" {
  name = "${local.base_name}-health-check"
  
  http_health_check {
    request_path = "/health"
    port         = "8080"
  }
  
  # OPTIMIZED TIMING
  check_interval_sec  = 10                        # Check every 10 seconds
  timeout_sec         = 5                         # 5 second timeout
  healthy_threshold   = 2                         # 2 successful checks = healthy
  unhealthy_threshold = 3                         # 3 failed checks = unhealthy
}
```

## 🎯 IMPLEMENTATION CHECKLIST

### Initial Setup
- [ ] Create GCS bucket for Terraform state storage
- [ ] Configure authentication (Service Account or ADC)
- [ ] Set up Terraform workspaces (`terraform workspace new dev`)
- [ ] Customize `settings/default.yaml` with your project details
- [ ] Create environment-specific YAML files (`dev.yaml`, `pre.yaml`, `pro.yaml`)

### Security Configuration  
- [ ] Plan the API enablement first (`terraform plan -target=google_project_service.project_apis`) and hand the apply to the user
- [ ] Review and customize IAM permissions
- [ ] Configure Secret Manager secrets with actual values
- [ ] Set up VPC network and firewall rules
- [ ] Enable audit logging and monitoring

### Application Deployment
- [ ] Deploy networking infrastructure first
- [ ] Deploy shared resources (databases, caches)
- [ ] Deploy application services  
- [ ] Configure load balancer and SSL certificates
- [ ] Set up monitoring and alerting

### Production Readiness
- [ ] Enable backup and disaster recovery
- [ ] Configure proper monitoring and alerting
- [ ] Set up CI/CD pipelines
- [ ] Implement proper secret rotation
- [ ] Document deployment procedures
- [ ] Train team on operational procedures

- [ ] Implement monitoring for every service, with consistent alert names and
      notification channels
- Set reasonable thresholds for alerts