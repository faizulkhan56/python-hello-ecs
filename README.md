# Python Hello ECS

A minimal **FastAPI** application packaged as a Docker image, pushed to **Amazon ECR**, and run on **Amazon ECS (Fargate)**. This repo is a hands-on lab for container build, registry, and orchestration on AWS — with optional **AWS CodePipeline** automation.

> **Region used in examples:** `ap-southeast-1` (Singapore). Keep ECR, ECS, CloudWatch, and pipeline in the **same region**.

---

## Table of contents

1. [What this project does](#what-this-project-does)
2. [Two deployment paths (read this first)](#two-deployment-paths-read-this-first)
3. [Configuration files explained](#configuration-files-explained)
4. [Architecture (theory)](#architecture-theory)
5. [Project structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Local development and Docker test](#local-development-and-docker-test)
8. [AWS setup — correct order (manual deploy)](#aws-setup--correct-order-manual-deploy)
9. [AWS Console walkthroughs](#aws-console-walkthroughs)
10. [Manual deploy workflow (code → ECR → ECS)](#manual-deploy-workflow-code--ecr--ecs)
11. [Optional: CodePipeline + CodeBuild](#optional-codepipeline--codebuild)
12. [Optional: CodeDeploy (blue/green)](#optional-codedeploy-bluegreen)
13. [Troubleshooting](#troubleshooting)
14. [Security notes](#security-notes)

---

## What this project does

| Endpoint | Response |
|----------|----------|
| `GET /` | JSON greeting with version and UTC timestamp |
| `GET /health` | `{"status": "ok"}` — for ECS / load-balancer health checks |

The app listens on **port 8000** inside the container. Uvicorn serves the FastAPI app in `app.py`.

---

## Two deployment paths (read this first)

| | **Path A — Manual (recommended for learning)** | **Path B — CodePipeline (automation)** |
|---|------------------------------------------------|----------------------------------------|
| **When to use** | First deploy, updates by hand | Push to GitHub triggers build + deploy |
| **Files you need** | `Dockerfile`, `app.py`, `ecs/task-definition.json` (reference) | Same + `buildspec.yml` |
| **Files you do NOT need** | `buildspec.yml`, `imagedefinitions.json`, `appspec.yaml` | — |
| **Build image** | Your laptop: `docker build` | CodeBuild runs `buildspec.yml` |
| **Push to ECR** | Your laptop: `docker push` | CodeBuild pushes automatically |
| **Update ECS** | Console: new task def revision + update service | Pipeline deploy stage uses `imagedefinitions.json` |

**Important:** `buildspec.yml`, `pipeline/imagedefinitions.json.example`, and `codedeploy/appspec.yaml` are for **Path B / CodeDeploy only**. They are **not used** when you deploy manually from your machine.

### Correct sequence for first-time AWS setup (Path A)

Do these steps **in this order**. Skipping or reordering causes common errors.

```text
Step 1  IAM role          ecsTaskExecutionRole (pull ECR + write logs)
Step 2  CloudWatch        Log group /ecs/python-hello-ecs
Step 3  ECR               Repository python-hello-ecs
Step 4  Local build       docker build + docker push :v1 to ECR
Step 5  ECS cluster       e.g. python-hello-cluster (Fargate)
Step 6  ECS task def      Family python-hello-ecs-task → image :v1
Step 7  ECS service       Links cluster + task def, desired count 1
Step 8  Test              Task public IP :8000 or ALB URL
```

Only after Step 7 works should you add CodePipeline (Path B).

---

## Configuration files explained

This section explains **what each file is**, **why it exists**, and **how they connect**.

### Relationship diagram

```text
YOUR APP CODE                         AWS PIPELINE FILES (Path B only)
─────────────                         ─────────────────────────────────

app.py ──────┐
requirements.txt ──┐
                   ├──► Dockerfile ──► docker build ──► ECR image
Dockerfile ────────┘         ▲                              │
                             │                              │
                    buildspec.yml ──── CodeBuild runs ───────┘
                    (build + push)              │
                                                ▼
                                    imagedefinitions.json
                                    (container name + image URI)
                                                │
                                                ▼
ecs/task-definition.json ◄──── ECS task definition (blueprint)
  - container name ─────────── must match imagedefinitions "name"
  - image URI ──────────────── updated each deploy
  - CPU, memory, ports, logs
                                                │
                                                ▼
                                    ECS Service (runs tasks on cluster)

codedeploy/appspec.yaml ──── ONLY for CodeDeploy blue/green
  - points at ECS service + ALB
  - NOT used by standard "Amazon ECS" pipeline deploy
```

### File reference

| File | Used when | What it does | Relationship to project |
|------|-----------|--------------|-------------------------|
| **`Dockerfile`** | Always | Builds the runtime image: Python 3.12, installs `requirements.txt`, copies `app.py`, starts Uvicorn on port 8000 | Defines **how** your app becomes a container. Manual deploy and CodeBuild both run `docker build` using this file. |
| **`ecs/task-definition.json`** | First ECS setup + CLI updates | JSON template for ECS **task definition**: Fargate CPU/memory, container name, ECR image URI, port 8000, CloudWatch logs, health check on `/health` | Tells ECS **what to run**. Container name `python-hello-ecs-container` must match `CONTAINER_NAME` in `buildspec.yml` and `imagedefinitions.json`. Replace `<YOUR_AWS_ACCOUNT_ID>` before registering. |
| **`buildspec.yml`** | CodePipeline / CodeBuild only | Instructions for CodeBuild: ECR login → `docker build` → `docker push` → write `imagedefinitions.json` artifact | Automates what you do manually with `docker build` + `docker push`. Lives in repo root so CodeBuild finds it automatically. |
| **`pipeline/imagedefinitions.json.example`** | Reference only | Example output format: `[{"name":"...","imageUri":"..."}]` | CodeBuild **generates** the real `imagedefinitions.json` at build time (see `buildspec.yml` post_build). The ECS **Deploy** stage reads that file to know which image to deploy. The `.example` file is documentation — do not commit generated `imagedefinitions.json`. |
| **`codedeploy/appspec.yaml`** | CodeDeploy blue/green only | Tells CodeDeploy which ECS service and load balancer listener to shift traffic during blue/green deployment | **Not needed** for manual deploy or standard CodePipeline "Amazon ECS" deploy. Only use when deploy provider is **CodeDeploy to ECS** with an ALB. |
| **`.env.example`** | Local reference | Placeholder values for AWS profile, account ID, cluster name, etc. | Copy to `.env` locally; never commit `.env`. |

### How `imagedefinitions.json` connects build → deploy

When CodePipeline runs:

1. **Source** stage pulls this GitHub repo (including `Dockerfile`, `buildspec.yml`, `app.py`).
2. **Build** stage (CodeBuild) executes `buildspec.yml`:
   - Builds image from `Dockerfile`
   - Pushes to ECR, e.g. `123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs:a1b2c3d`
   - Creates artifact `imagedefinitions.json`:
     ```json
     [{"name":"python-hello-ecs-container","imageUri":"123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs:a1b2c3d"}]
     ```
3. **Deploy** stage (Amazon ECS) reads `imagedefinitions.json`, registers a **new task definition revision** with that image, and **updates the ECS service**.

The `name` field must exactly match the container name in your ECS task definition (`python-hello-ecs-container`).

### Manual deploy vs pipeline — same end result

| Action | Manual (you) | Pipeline (automated) |
|--------|--------------|----------------------|
| Build image | `docker build -t python-hello-ecs:v2 .` | `buildspec.yml` → `docker build` |
| Push to ECR | `docker push ...:v2` | `buildspec.yml` → `docker push` |
| Tell ECS new image | Edit task def image URI in console | `imagedefinitions.json` from CodeBuild |
| Roll out | Update service + force deployment | ECS deploy stage |

---

## Architecture (theory)

```text
Developer machine                AWS
─────────────────               ─────────────────────────────────────────
  app.py + Dockerfile
        │
        ▼
  docker build  ──────────────►  Amazon ECR (private Docker registry)
        │                              │
        ▼                              ▼
  docker run (local test)        Amazon ECS Cluster
                                        │
                                        ▼
                                 ECS Service (keeps N tasks running)
                                        │
                                        ▼
                                 ECS Task (containers from task definition)
                                        │
                                        ▼
                                 ALB (optional) → users
```

| Term | Meaning |
|------|---------|
| **ECR** | Private Docker registry in AWS |
| **ECS cluster** | Logical group where tasks run (Fargate = no EC2 to manage) |
| **Task definition** | Blueprint: image, CPU, memory, ports, roles, logging |
| **Task** | One running copy of a task definition |
| **Service** | Keeps desired task count; replaces failed tasks; handles rolling deploys |

**How task links to cluster:** You do not "attach" a task to a cluster directly. You create an **ECS service** on a **cluster** and point it at a **task definition**. The service starts tasks on that cluster.

---

## Project structure

```text
python-hello-ecs/
├── app.py                              # FastAPI app
├── requirements.txt
├── Dockerfile                          # Image build (always used)
├── buildspec.yml                       # CodeBuild only (Path B)
├── .env.example                        # Local placeholders
├── ecs/
│   └── task-definition.json            # ECS blueprint template
├── codedeploy/
│   └── appspec.yaml                    # CodeDeploy blue/green only
└── pipeline/
    └── imagedefinitions.json.example   # Format reference (not used at runtime)
```

---

## Prerequisites

**Local:** Docker Desktop, AWS CLI v2, Git (Python 3.12+ optional for local dev).

**AWS (first time):** IAM role, CloudWatch log group, ECR repo, ECS cluster, task definition, service — see ordered steps below.

Copy `.env.example` → `.env` locally. **Never commit `.env`.**

---

## Local development and Docker test

### Run without Docker

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
curl http://localhost:8000
```

### Run with Docker (do this before AWS)

```bash
docker build -t python-hello-ecs:local .
docker run --rm -p 8000:8000 --name python-hello-container python-hello-ecs:local
```

Background mode: `docker run -d -p 8000:8000 --name python-hello-container python-hello-ecs:local`

Use **`-d` only** — avoid **`-dit`** (can leave container in `Created` state without running).

Verify: `curl http://localhost:8000` and `curl http://localhost:8000/health`

---

## AWS setup — correct order (manual deploy)

Complete [Local Docker test](#run-with-docker-do-this-before-aws) first, then follow Steps 1–8 in order.

---

## AWS Console walkthroughs

### Step 1 — IAM role: `ecsTaskExecutionRole`

**Why:** ECS needs this role to pull your image from ECR and send logs to CloudWatch.

**Console:** IAM → **Roles** → **Create role**

| Screen | Choose |
|--------|--------|
| Trusted entity | **AWS service** → **Elastic Container Service** → **Elastic Container Service Task** |
| Permissions | Attach **`AmazonECSTaskExecutionRolePolicy`** |
| Role name | `ecsTaskExecutionRole` |

**Verify:** Role exists with trust policy for `ecs-tasks.amazonaws.com`.

> This lab app does not call AWS APIs from inside the container, so a separate **task role** is not required.

---

### Step 2 — CloudWatch log group

**Why:** Task definition sends container logs to `/ecs/python-hello-ecs`. The group must exist before tasks start.

**Console:** CloudWatch → **Log groups** → **Create log group**

| Field | Value |
|-------|-------|
| Log group name | `/ecs/python-hello-ecs` |
| Retention | 7 days (lab) or as needed |

---

### Step 3 — ECR repository

**Why:** Stores your Docker images privately in AWS.

**Console:** Amazon ECR → **Repositories** → **Create repository**

| Field | Value |
|-------|-------|
| Repository name | `python-hello-ecs` |
| Tag immutability | Optional (off for lab) |
| Scan on push | Optional (recommended) |

Note the **URI** on the repository page, e.g.:

```text
<YOUR_AWS_ACCOUNT_ID>.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs
```

---

### Step 4 — Build and push first image to ECR

**Why:** ECS task definition must reference an image that **already exists** in ECR.

**Git Bash:**

```bash
export AWS_PROFILE=<YOUR_AWS_CLI_PROFILE>
export AWS_REGION=ap-southeast-1
export AWS_ACCOUNT_ID=<YOUR_AWS_ACCOUNT_ID>
export ECR_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/python-hello-ecs

aws ecr get-login-password --region $AWS_REGION --profile $AWS_PROFILE \
  | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

docker build -t python-hello-ecs:v1 .
docker tag python-hello-ecs:v1 $ECR_URI:v1
docker push $ECR_URI:v1
```

**Verify in console:** ECR → `python-hello-ecs` → **Images** tab shows tag `v1`.

---

### Step 5 — ECS cluster

**Why:** A cluster is the place where ECS runs your tasks.

**Console:** Amazon ECS → **Clusters** → **Create cluster**

| Field | Value |
|-------|-------|
| Cluster name | `python-hello-cluster` |
| Infrastructure | **AWS Fargate (serverless)** |

Click **Create**. No EC2 instances needed for Fargate.

---

### Step 6 — ECS task definition

**Why:** Defines the container image, resources, port, logging, and IAM role for each task.

**Console:** ECS → **Task definitions** → **Create new task definition** → **Create new task definition with JSON** (or use the form wizard)

**Option A — Console form (wizard)**

| Section | Value |
|---------|-------|
| Task definition family | `python-hello-ecs-task` |
| Launch type | **AWS Fargate** |
| OS/arch | Linux / X86_64 |
| Task size CPU | `.25 vCPU` |
| Task size Memory | `.5 GB` (512 MB) |
| Task role | None (leave empty for this lab) |
| Task execution role | `ecsTaskExecutionRole` |
| Container name | `python-hello-ecs-container` |
| Image URI | `<ACCOUNT>.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs:v1` |
| Port | `8000` TCP |
| Log collection | **Amazon CloudWatch** → log group `/ecs/python-hello-ecs` → stream prefix `ecs` |

Click **Create**.

**Option B — CLI using repo template**

1. Edit `ecs/task-definition.json`: replace `<YOUR_AWS_ACCOUNT_ID>`, set image to `:v1`.
2. Run:

```bash
aws ecs register-task-definition \
  --cli-input-json file://ecs/task-definition.json \
  --region ap-southeast-1 \
  --profile <YOUR_AWS_CLI_PROFILE>
```

**Verify:** Task definitions → `python-hello-ecs-task` → revision `1` (or higher).

---

### Step 7 — ECS service

**Why:** The service keeps your app running (desired count = 1) and handles replacements during deploys.

**Console:** ECS → **Clusters** → `python-hello-cluster` → **Create service**

| Section | Value |
|---------|-------|
| Compute options | **Launch type** → Fargate |
| Application type | **Service** |
| Task definition | `python-hello-ecs-task:latest` |
| Service name | `python-hello-service` |
| Desired tasks | `1` |
| Deployment type | **Rolling update** (default) |
| VPC | Default VPC |
| Subnets | Select **public** subnets (at least one) |
| Security group | Create new or select existing — **inbound TCP 8000** from your IP (lab) or from ALB SG |
| Public IP | **Turned on** (required if no NAT gateway and using public subnet) |
| Load balancer | **None** for simple lab (use task public IP) |

Click **Create**.

**Wait:** Cluster → **Services** → `python-hello-service` → **Tasks** tab → task status **RUNNING**.

**Get URL:** Click the task → under **Configuration** copy **Public IP** → open `http://<PUBLIC_IP>:8000`.

**Verify JSON** shows `"message": "Hello from Python app running on AWS ECS!"`.

---

### Step 8 — (Optional) Application Load Balancer

Use an ALB for production-style access (stable DNS, HTTPS, health checks). Not required for the lab if you use task public IP.

If you add ALB later:

- Target group: port **8000**, health check path **`/health`**
- Service update: attach load balancer, container `python-hello-ecs-container:8000`
- Security group: allow ALB → task on 8000; users hit ALB DNS only

---

## Manual deploy workflow (code → ECR → ECS)

Use this for every code change when **not** using CodePipeline.

| Step | Action |
|------|--------|
| 1 | Edit code (e.g. `"version": "v2"` in `app.py`) |
| 2 | `git commit` + optional `git tag v2 && git push origin v2` |
| 3 | `docker build -t python-hello-ecs:v2 .` |
| 4 | ECR login + `docker tag` + `docker push ...:v2` |
| 5 | ECS → Task definitions → **Create new revision** → change image to `:v2` |
| 6 | ECS → Service → **Update** → new revision → **Force new deployment** |
| 7 | Wait for new task **RUNNING** → test URL → confirm new version in JSON |

**CLI update (after editing `ecs/task-definition.json` image to `:v2`):**

```bash
aws ecs register-task-definition --cli-input-json file://ecs/task-definition.json \
  --region ap-southeast-1 --profile <YOUR_AWS_CLI_PROFILE>

aws ecs update-service \
  --cluster python-hello-cluster \
  --service python-hello-service \
  --task-definition python-hello-ecs-task:<REVISION> \
  --force-new-deployment \
  --region ap-southeast-1 --profile <YOUR_AWS_CLI_PROFILE>
```

---

## Optional: CodePipeline + CodeBuild

Set this up **only after** manual Path A works (ECR + ECS service exist).

### What you create in AWS

| Resource | Purpose |
|----------|---------|
| GitHub connection | CodePipeline pulls source from GitHub |
| CodeBuild project | Runs `buildspec.yml` |
| CodePipeline | Wires Source → Build → Deploy |
| IAM roles | CodeBuild role (ECR push), CodePipeline role (ECS update) |

### Step 1 — GitHub connection

**Console:** CodePipeline → **Settings** → **Connections** → **Create connection** → **GitHub** → authorize → name e.g. `github-python-hello-ecs`.

### Step 2 — CodeBuild project

**Console:** CodeBuild → **Build projects** → **Create build project**

| Field | Value |
|-------|-------|
| Project name | `python-hello-ecs-build` |
| Source | **GitHub** (or Pipeline if created via wizard) |
| Environment image | **Managed image**, Amazon Linux, **Standard** runtime |
| Privileged | **✓ Enabled** (required for `docker build`) |
| Service role | New or existing with ECR push permissions |
| Buildspec | **Use a buildspec file** → `buildspec.yml` |

**Environment variables** (required):

| Name | Value |
|------|-------|
| `AWS_ACCOUNT_ID` | `<YOUR_AWS_ACCOUNT_ID>` |
| `IMAGE_REPO_NAME` | `python-hello-ecs` |
| `CONTAINER_NAME` | `python-hello-ecs-container` |

`AWS_DEFAULT_REGION` is set automatically from the project region.

**CodeBuild IAM policy (attach to service role):** AWS managed **`AmazonEC2ContainerRegistryPowerUser`** plus CloudWatch Logs, or custom policy with `ecr:*` push actions listed in AWS docs.

### Step 3 — CodePipeline

**Console:** CodePipeline → **Create pipeline**

| Stage | Provider | Settings |
|-------|----------|----------|
| **1 Source** | GitHub (Version 2) | Connection, repo `python-hello-ecs`, branch `main` |
| **2 Build** | AWS CodeBuild | Project `python-hello-ecs-build` |
| **3 Deploy** | **Amazon ECS** | Cluster `python-hello-cluster`, service `python-hello-service`, image definitions file: **`imagedefinitions.json`** |

**Deploy provider must be "Amazon ECS"** — not CodeDeploy — for the standard `buildspec.yml` in this repo.

Pipeline role needs ECS update permissions; the create wizard can auto-create **`AWSCodePipelineServiceRole`**.

### Step 4 — Trigger and verify

```bash
git push origin main
```

Watch pipeline: Source → Build (CodeBuild logs) → Deploy (ECS service update). Confirm new task running and app responds with updated version.

---

## Optional: CodeDeploy (blue/green)

**When:** Production setups with ALB, zero-downtime traffic shifting.

**This repo's `codedeploy/appspec.yaml` is for this path only.**

| Standard ECS deploy (this repo default) | CodeDeploy blue/green |
|----------------------------------------|-------------------------|
| Uses `imagedefinitions.json` | Uses `appspec.yaml` + task definition |
| Simpler, good for labs | Needs ALB, two target groups, CodeDeploy application |
| Pipeline deploy provider: **Amazon ECS** | Pipeline deploy provider: **CodeDeploy to ECS** |

**`appspec.yaml` role:** Tells CodeDeploy which ECS **service** to update and which **container:port** receives load balancer traffic during a blue/green deployment. CodeDeploy creates a new task set (green), shifts ALB traffic, then drains the old set (blue).

For this learning project, **skip CodeDeploy** unless you already have an ALB and want blue/green practice.

---

## Troubleshooting

### Container `Created` but not running (local Docker)

```bash
docker start python-hello-container
# or
docker rm python-hello-container
docker run -d -p 8000:8000 --name python-hello-container python-hello-ecs:local
```

### Docker Hub `unexpected EOF` on `FROM python:3.12-slim`

Network/Docker Hub issue — not your code. Retry, `docker pull python:3.12-slim`, `docker login`, restart Docker Desktop, or `docker build --pull=false ...`.

### ECR push denied

Re-login (token expires in 12 hours):

```bash
aws ecr get-login-password --region ap-southeast-1 --profile <PROFILE> \
  | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.ap-southeast-1.amazonaws.com
```

### ECS task `CannotPullContainerError`

- Image tag exists in ECR (same region)
- Task execution role is `ecsTaskExecutionRole` with ECR permissions
- Image URI in task definition is exact (account, region, repo, tag)

### ECS task stops — log group not found

Create CloudWatch log group `/ecs/python-hello-ecs` **before** starting tasks.

### Task PENDING forever

- Fargate needs subnets selected on the service
- Enable **Public IP** if image pull goes through internet and no NAT
- Security group must allow **outbound** traffic

### Service updated but old version still shown

1. Confirm `:v2` (or new tag) in ECR
2. New task definition **revision** uses new image URI
3. **Force new deployment** on service
4. Wait for old task to stop; test **new** task public IP

### CodePipeline build fails

| Error | Fix |
|-------|-----|
| Docker daemon | Enable **Privileged** on CodeBuild |
| `AWS_ACCOUNT_ID` unset | Add env var on CodeBuild project |
| Deploy fails | `CONTAINER_NAME` must be `python-hello-ecs-container` everywhere |
| ECR denied | CodeBuild role needs ECR push policy |

### Cannot open app in browser

| Case | Fix |
|------|-----|
| Local | `http://localhost:8000` |
| ECS no ALB | Task **Public IP**, SG allows **8000** from your IP |
| ECS with ALB | ALB DNS name; target health on `/health` |

---

## Security notes

**No secrets in this repository** — safe for GitHub. Use placeholders in `.env.example` only.

Do not commit: `.env`, AWS access keys, Docker credentials.

Use IAM roles for CodeBuild/CodePipeline/ECS in AWS, not long-lived keys in the repo.

---

## Quick reference

```bash
# Local test
docker build -t python-hello-ecs:local .
docker run --rm -p 8000:8000 python-hello-ecs:local

# Push v2 manually
docker build -t python-hello-ecs:v2 .
docker tag python-hello-ecs:v2 <ACCOUNT>.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs:v2
docker push <ACCOUNT>.dkr.ecr.ap-southeast-1.amazonaws.com/python-hello-ecs:v2

# Force ECS redeploy
aws ecs update-service --cluster python-hello-cluster --service python-hello-service \
  --force-new-deployment --region ap-southeast-1 --profile <PROFILE>
```

---

## License

MIT — use freely for learning and workshops.
