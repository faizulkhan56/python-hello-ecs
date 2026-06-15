# Python Hello ECS

A minimal **FastAPI** application packaged as a Docker image, pushed to **Amazon ECR**, and run on **Amazon ECS (Fargate)**. This repo is a hands-on lab for container build, registry, and orchestration on AWS — with optional **AWS CodePipeline** automation.

> **Region used in examples:** `ap-southeast-1` (Singapore). Keep ECR, ECS, CloudWatch, and pipeline in the **same region**.

---

## Table of contents

**Hands-on path (do in order)**

1. [Complete end-to-end journey](#complete-end-to-end-journey-first--last)
2. [Prerequisites](#prerequisites)
3. [Phase 1 — Scaffold the Python project](#phase-1--scaffold-the-python-project)
4. [Phase 2 — Containerize with Docker](#phase-2--containerize-with-docker)
5. [Phase 3 — Push code to GitHub](#phase-3--push-code-to-github)
6. [Phase 4 — AWS setup (manual deploy)](#phase-4--aws-setup-manual-deploy)
7. [AWS Console walkthroughs (Phase 4 details)](#phase-4--aws-console-walkthroughs)
8. [Phase 5 — Update app (code → ECR → ECS)](#phase-5--update-app-code--ecr--ecs)
9. [Phase 6 — CodePipeline (optional)](#phase-6--codepipeline-optional)

**Reference**

10. [Reference (files, architecture, paths)](#reference)
11. [Troubleshooting](#troubleshooting)
12. [Security notes](#security-notes)

---

## Complete end-to-end journey (first → last)

Follow these phases **in order**. Each phase builds on the previous one.

```text
PHASE 1 — PYTHON PROJECT (your laptop)
  1.1  Create project folder
  1.2  Create virtual environment
  1.3  Create requirements.txt
  1.4  Create app.py (FastAPI)
  1.5  Install dependencies + run locally with uvicorn
  1.6  Test http://localhost:8000

PHASE 2 — DOCKER (your laptop)
  2.1  Create Dockerfile
  2.2  Create .dockerignore
  2.3  docker build
  2.4  docker run + test http://localhost:8000

PHASE 3 — GIT / GITHUB (your laptop)
  3.1  Create .gitignore
  3.2  git init → commit → push to GitHub

PHASE 4 — AWS FIRST DEPLOY (AWS Console + CLI)
  4.1  IAM role ecsTaskExecutionRole
  4.2  CloudWatch log group /ecs/python-hello-ecs
  4.3  ECR repository python-hello-ecs
  4.4  docker push :v1 to ECR
  4.5  ECS cluster (Fargate)
  4.6  ECS task definition → image :v1
  4.7  ECS service → desired count 1
  4.8  Test http://<TASK_PUBLIC_IP>:8000

PHASE 5 — APP UPDATES (repeat whenever code changes)
  5.1  Edit app.py (e.g. version v2)
  5.2  docker build + push :v2 to ECR
  5.3  New task definition revision + update ECS service

PHASE 6 — CODEPIPELINE (optional, after Phase 4 works)
  6.1  GitHub connection
  6.2  CodeBuild project (buildspec.yml)
  6.3  CodePipeline Source → Build → Deploy
```

> **Already cloned this repo?** You can start at [Phase 2](#phase-2--containerize-with-docker) (Docker) or [Phase 4](#phase-4--aws-setup-manual-deploy) (AWS) if Python scaffolding is done.

---

## Prerequisites

Install these **before Phase 1**:

| Tool | Purpose | Check |
|------|---------|-------|
| **Python 3.12+** | Local dev and virtual environment | `python --version` |
| **pip** | Install Python packages | `pip --version` |
| **Docker Desktop** | Build and test containers locally | `docker --version` |
| **Git** | Version control and GitHub push | `git --version` |
| **AWS CLI v2** | ECR login, ECS commands (Phase 4+) | `aws --version` |
| **AWS account** | ECR, ECS, IAM (Phase 4+) | Console login works |

Copy `.env.example` → `.env` locally before Phase 4. **Never commit `.env`.**

---

## Phase 1 — Scaffold the Python project

This phase creates the Python app **from scratch**. If you cloned this repo, the files already exist — skim to understand what each file does, then run the test commands.

### 1.1 Create project folder

```bash
mkdir python-hello-ecs
cd python-hello-ecs
```

### 1.2 Create virtual environment

A virtual environment keeps project dependencies isolated from your system Python.

```bash
python -m venv .venv
```

**Activate it:**

```bash
# Git Bash / Linux / macOS
source .venv/Scripts/activate

# PowerShell
.venv\Scripts\Activate.ps1

# CMD
.venv\Scripts\activate.bat
```

Your prompt should show `(.venv)`. While active, `pip install` affects only this project.

### 1.3 Create `requirements.txt`

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
```

| Package | Role |
|---------|------|
| **fastapi** | Web framework — defines routes like `/` and `/health` |
| **uvicorn** | ASGI server — runs the FastAPI app (like Gunicorn for Flask) |

### 1.4 Create `app.py`

```python
from fastapi import FastAPI
from datetime import datetime

app = FastAPI()


@app.get("/")
def home():
    return {
        "message": "Hello from Python app running on AWS ECS!",
        "version": "v1",
        "time": datetime.utcnow().isoformat()
    }


@app.get("/health")
def health():
    return {"status": "ok"}
```

| Route | Purpose |
|-------|---------|
| `GET /` | Main response — proves the app is running |
| `GET /health` | Health check — used by ECS and load balancers |

### 1.5 Install dependencies and run locally

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

| Flag | Meaning |
|------|---------|
| `app:app` | Module `app.py`, variable `app = FastAPI()` |
| `--host 0.0.0.0` | Listen on all interfaces (required inside Docker/ECS later) |
| `--port 8000` | Port the app listens on |
| `--reload` | Auto-restart on code change (local dev only; not used in Docker CMD) |

### 1.6 Test locally

Open another terminal (keep uvicorn running):

```bash
curl http://localhost:8000
curl http://localhost:8000/health
```

Or open **http://localhost:8000** in a browser. You should see JSON with `"message"`, `"version"`, and `"time"`.

Stop uvicorn with `Ctrl+C` when done.

**Phase 1 complete when:** both endpoints return JSON locally.

---

## Phase 2 — Containerize with Docker

Docker packages your Python app so it runs the same on your laptop, in ECR, and on ECS.

### 2.1 Create `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

| Line | Why |
|------|-----|
| `FROM python:3.12-slim` | Base image with Python 3.12 (small Linux image) |
| `WORKDIR /app` | Working directory inside the container |
| `COPY` + `RUN pip install` | Install deps before copying app code (better layer caching) |
| `EXPOSE 8000` | Documents the port (ECS task definition must match) |
| `CMD uvicorn ...` | Starts the app when the container runs (no `--reload` in production) |

### 2.2 Create `.dockerignore`

```text
.venv
__pycache__
.git
.gitignore
*.pyc
.env
.env.*
!.env.example
pipeline/imagedefinitions.json
```

Keeps virtual env, git metadata, and secrets out of the image (smaller, safer builds).

### 2.3 Build the image

```bash
docker build -t python-hello-ecs:local .
```

### 2.4 Run and test the container

**Foreground (recommended for first test):**

```bash
docker run --rm -p 8000:8000 --name python-hello-container python-hello-ecs:local
```

**Background:**

```bash
docker run -d -p 8000:8000 --name python-hello-container python-hello-ecs:local
```

Use **`-d` only** — avoid **`-dit`** (can leave container in `Created` state without running).

Test:

```bash
curl http://localhost:8000
curl http://localhost:8000/health
docker logs python-hello-container
```

Clean up background container:

```bash
docker stop python-hello-container
docker rm python-hello-container
```

**Phase 2 complete when:** container responds on `http://localhost:8000` the same as Phase 1.

---

## Phase 3 — Push code to GitHub

Version control before AWS. CodePipeline (Phase 6) also needs a GitHub repo.

### 3.1 Create `.gitignore`

Ensure at minimum:

```text
.venv/
__pycache__/
.env
.env.*
!.env.example
.aws/
```

(Full list is in this repo's `.gitignore`.)

### 3.2 Copy env template (before Phase 4)

```bash
cp .env.example .env
# Edit .env with your AWS profile and account ID — never commit .env
```

### 3.3 Initialize Git and push

```bash
git init
git add app.py requirements.txt Dockerfile .dockerignore .gitignore
git add README.md ecs/ buildspec.yml codedeploy/ pipeline/ .env.example
git commit -m "Initial Python FastAPI app with Docker and ECS config"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USER>/python-hello-ecs.git
git push -u origin main
```

**Phase 3 complete when:** code is visible on GitHub. Do **not** commit `.env` or `.venv/`.

---

## Phase 4 — AWS setup (manual deploy)

Complete [Phase 2](#phase-2--containerize-with-docker) first. Do these AWS steps **in this order**:

```text
Step 1  IAM role          ecsTaskExecutionRole
Step 2  CloudWatch        Log group /ecs/python-hello-ecs
Step 3  ECR               Repository python-hello-ecs
Step 4  Push image        docker build + docker push :v1
Step 5  ECS cluster       python-hello-cluster (Fargate)
Step 6  ECS task def      python-hello-ecs-task → image :v1
Step 7  ECS service       python-hello-service, desired count 1
Step 8  Test              http://<TASK_PUBLIC_IP>:8000
```

Only after Step 8 works should you add [CodePipeline (Phase 6)](#phase-6--codepipeline-optional).

### Phase 4 — AWS Console walkthroughs

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

## Phase 5 — Update app (code → ECR → ECS)

Repeat this phase whenever you change code and **are not** using CodePipeline (Phase 6).

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

## Phase 6 — CodePipeline (optional)

Set this up **only after [Phase 4](#phase-4--aws-setup-manual-deploy) works** (ECR + ECS service running).

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

## CodeDeploy blue/green (optional)

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

## Reference

### What this project does

| Endpoint | Response |
|----------|----------|
| `GET /` | JSON greeting with version and UTC timestamp |
| `GET /health` | `{"status": "ok"}` — for ECS / load-balancer health checks |

The app listens on **port 8000** inside the container. Uvicorn serves the FastAPI app in `app.py`.

### Two deployment paths

| | **Path A — Manual (Phases 1–5)** | **Path B — CodePipeline (Phase 6)** |
|---|----------------------------------|-------------------------------------|
| **When to use** | First deploy and learning | Push to GitHub triggers build + deploy |
| **Files you need** | `app.py`, `Dockerfile`, `ecs/task-definition.json` | Same + `buildspec.yml` |
| **Files you do NOT need** | `buildspec.yml`, `imagedefinitions.json`, `appspec.yaml` | — |
| **Build image** | Phase 2 / 5: `docker build` on your laptop | CodeBuild runs `buildspec.yml` |
| **Push to ECR** | Phase 4 / 5: `docker push` | CodeBuild pushes automatically |
| **Update ECS** | Phase 4 / 5: task def revision + update service | Pipeline deploy uses `imagedefinitions.json` |

**Important:** `buildspec.yml`, `pipeline/imagedefinitions.json.example`, and `codedeploy/appspec.yaml` are for **Path B / CodeDeploy only**. They are **not used** in Phases 1–5 (manual path).

### Configuration files explained

| File | Used when | What it does |
|------|-----------|--------------|
| **`Dockerfile`** | Phases 2, 4, 5, 6 | Builds the container image from `app.py` + dependencies |
| **`ecs/task-definition.json`** | Phase 4, 5 | ECS blueprint: CPU, ports, logs, container name + image URI |
| **`buildspec.yml`** | Phase 6 only | CodeBuild: build, push to ECR, generate `imagedefinitions.json` |
| **`pipeline/imagedefinitions.json.example`** | Reference | Shows format CodeBuild outputs for ECS deploy stage |
| **`codedeploy/appspec.yaml`** | CodeDeploy only | Blue/green traffic shifting with ALB |
| **`.env.example`** | Phase 4+ locally | Placeholder AWS values — copy to `.env`, never commit |

Container name **`python-hello-ecs-container`** must match in `task-definition.json`, `buildspec.yml`, and `imagedefinitions.json`.

### Architecture (theory)

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

### Project structure

```text
python-hello-ecs/
├── app.py                              # Phase 1 — FastAPI app
├── requirements.txt                    # Phase 1 — Python dependencies
├── Dockerfile                          # Phase 2 — image build
├── .dockerignore                       # Phase 2 — exclude .venv from image
├── .gitignore                          # Phase 3 — exclude secrets from Git
├── buildspec.yml                       # Phase 6 — CodeBuild only
├── .env.example                        # Phase 4 — local AWS placeholders
├── ecs/
│   └── task-definition.json            # Phase 4 — ECS blueprint
├── codedeploy/
│   └── appspec.yaml                    # CodeDeploy blue/green only
└── pipeline/
    └── imagedefinitions.json.example   # Phase 6 — format reference
```

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
