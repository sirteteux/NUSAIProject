# GitHub CI/CD Setup Guide - Microservices

## 🎯 Overview

Simple CI/CD workflows for your HR Microservices project with GitHub Actions.

---

## 📋 Available Workflows

### 1. **ci-cd.yml** - Main CI/CD Pipeline
**Triggers:** Push to main/develop, Pull Requests
**Jobs:**
- ✅ Test all 9 services
- ✅ Build and push Docker images (on main)
- ✅ Deploy to staging (on develop)
- ✅ Deploy to production (on main)

### 2. **test.yml** - Test Only
**Triggers:** All pushes and PRs
**Jobs:**
- ✅ Quick test of all services
- ✅ No deployment

### 3. **deploy-ec2.yml** - AWS EC2 Deployment
**Triggers:** Push to main, Manual
**Jobs:**
- ✅ SSH to EC2
- ✅ Pull latest code
- ✅ Docker Compose deployment
- ✅ Health checks
- ✅ Slack notifications

### 4. **deploy-k8s.yml** - Kubernetes Deployment
**Triggers:** Push to main, Manual
**Jobs:**
- ✅ Deploy to EKS/GKE/AKS
- ✅ Rolling updates
- ✅ Health verification

---

## 🚀 Quick Setup (5 Minutes)

### Step 1: Create GitHub Repository

```bash
cd hr-microservices

# Initialize git
git init
git add .
git commit -m "Initial commit - Microservices with CI/CD"

# Create repo on github.com
# Then add remote:
git remote add origin https://github.com/YOUR_USERNAME/hr-microservices.git
git branch -M main
git push -u origin main
```

### Step 2: Configure GitHub Secrets

Go to: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

#### Required Secrets:

| Secret Name | Value | Used For |
|------------|-------|----------|
| `OPENAI_API_KEY` | `sk-...` | AI services |
| `MONGO_USERNAME` | `admin` | MongoDB |
| `MONGO_PASSWORD` | `securepass123` | MongoDB |
| `JWT_SECRET` | `your-secret-key` | Auth service |

#### For AWS EC2 Deployment:

| Secret Name | Value | Used For |
|------------|-------|----------|
| `AWS_ACCESS_KEY_ID` | Your AWS key | AWS authentication |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret | AWS authentication |
| `AWS_REGION` | `us-east-1` | AWS region |
| `EC2_HOST` | `ec2-xxx.compute.amazonaws.com` | EC2 instance |
| `EC2_USER` | `ubuntu` | SSH user |
| `EC2_SSH_KEY` | `-----BEGIN RSA...` | SSH private key |

#### For Kubernetes Deployment:

| Secret Name | Value | Used For |
|------------|-------|----------|
| `EKS_CLUSTER_NAME` | `hr-cluster` | Kubernetes cluster |
| `MONGODB_URI` | `mongodb+srv://...` | Production MongoDB |

#### Optional (for notifications):

| Secret Name | Value | Used For |
|------------|-------|----------|
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` | Slack notifications |

### Step 3: Enable GitHub Packages

1. Go to **Settings** → **Actions** → **General**
2. Under **Workflow permissions**:
   - ✅ Select "Read and write permissions"
   - ✅ Check "Allow GitHub Actions to create and approve pull requests"
3. Click **Save**

### Step 4: Create Branches

```bash
# Create develop branch
git checkout -b develop
git push -u origin develop

# Back to main
git checkout main
```

### Step 5: Test the Workflow

```bash
# Make a change
echo "# Test" >> README.md
git add README.md
git commit -m "test: Trigger CI/CD"
git push

# Go to GitHub → Actions tab to see it running!
```

---

## 📊 Workflow Details

### Main CI/CD Pipeline Flow

```
Push to main/develop
  ↓
Test All Services (9 services)
  ↓
Build Docker Images (on main only)
  ↓ (parallel builds)
  ├─ API Gateway
  ├─ Auth Service
  ├─ FAQ Service
  ├─ Payroll Service
  ├─ Leave Service
  ├─ Recruitment Service
  ├─ Performance Service
  ├─ Coordinator Service
  └─ Frontend
  ↓
Push to GitHub Container Registry
  ↓
Deploy to Environment
  ├─ Staging (if develop branch)
  └─ Production (if main branch)
```

---

## 🐳 Docker Images

All images are published to GitHub Container Registry:

```
ghcr.io/YOUR_USERNAME/hr-microservices/api-gateway:latest
ghcr.io/YOUR_USERNAME/hr-microservices/auth-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/faq-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/payroll-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/leave-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/recruitment-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/performance-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/coordinator-service:latest
ghcr.io/YOUR_USERNAME/hr-microservices/frontend:latest
```

### Pull Images

```bash
# Login
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Pull all images
docker pull ghcr.io/YOUR_USERNAME/hr-microservices/api-gateway:latest
docker pull ghcr.io/YOUR_USERNAME/hr-microservices/auth-service:latest
# ... etc
```

---

## 🎯 Development Workflow

### Feature Development

```bash
# 1. Create feature branch
git checkout -b feature/new-service

# 2. Make changes
# ... code ...

# 3. Commit and push
git add .
git commit -m "feat: Add new service feature"
git push origin feature/new-service

# 4. Create Pull Request on GitHub
# → Tests run automatically

# 5. After PR approved, merge to develop
# → Deploys to STAGING

# 6. When ready, merge develop → main
# → Deploys to PRODUCTION
```

### Hotfix

```bash
# 1. Create hotfix branch from main
git checkout main
git checkout -b hotfix/critical-bug

# 2. Fix the bug
# ... code ...

# 3. Push and create PR
git push origin hotfix/critical-bug

# 4. Merge to main
# → Deploys directly to PRODUCTION
```

---

## 🚀 Deployment Options

### Option 1: AWS EC2 (Simplest)

**Setup:**
1. Launch EC2 instance (Ubuntu 22.04, t3.medium)
2. Install Docker and Docker Compose
3. Clone repo to `/home/ubuntu/hr-microservices`
4. Configure secrets in GitHub
5. Push to main → Auto-deploys

**Workflow:** `deploy-ec2.yml`

### Option 2: Kubernetes (Production)

**Setup:**
1. Create EKS/GKE/AKS cluster
2. Apply Kubernetes manifests from `infrastructure/kubernetes/`
3. Configure secrets in GitHub
4. Push to main → Rolling update

**Workflow:** `deploy-k8s.yml`

### Option 3: Manual Deployment

```bash
# On your server
cd /app
git pull
docker-compose down
docker-compose pull
docker-compose up -d
```

---

## 📋 Customizing Workflows

### Change Deployment Target

Edit `.github/workflows/deploy-ec2.yml`:

```yaml
- name: Deploy to EC2
  uses: appleboy/ssh-action@v1.0.0
  with:
    host: ${{ secrets.EC2_HOST }}
    username: ${{ secrets.EC2_USER }}
    key: ${{ secrets.EC2_SSH_KEY }}
    script: |
      cd /home/ubuntu/hr-microservices
      git pull origin main
      docker-compose pull
      docker-compose up -d
```

### Add Slack Notifications

Already included in `deploy-ec2.yml`! Just add `SLACK_WEBHOOK_URL` secret.

### Change Build Triggers

Edit `.github/workflows/ci-cd.yml`:

```yaml
on:
  push:
    branches: [ main, develop, staging ]  # Add more branches
```

---

## 🧪 Testing Workflows Locally

### Install act (GitHub Actions locally)

```bash
# macOS
brew install act

# Linux
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

### Run Workflow Locally

```bash
# Test the test workflow
act -j test-all

# Test build workflow
act -j build
```

---

## 📊 Monitoring CI/CD

### View Workflow Runs
1. Go to your repository
2. Click **Actions** tab
3. See all workflow runs and logs

### Add Status Badges

Add to your README.md:

```markdown
![CI/CD](https://github.com/YOUR_USERNAME/hr-microservices/workflows/Microservices%20CI/CD/badge.svg)
![Tests](https://github.com/YOUR_USERNAME/hr-microservices/workflows/Test%20All%20Services/badge.svg)
```

### Check Docker Images
1. Go to your repository
2. Click **Packages** on the right sidebar
3. View all published images

---

## 🐛 Troubleshooting

### Build Fails: "Permission denied"

**Solution:**
- Settings → Actions → General → Workflow permissions
- Select "Read and write permissions"
- Save

### Build Fails: "denied: installation not allowed to Write organization package"

**Solution:**
Add to workflow:
```yaml
permissions:
  contents: read
  packages: write
```

### Deployment Fails: "Could not connect to EC2"

**Solution:**
- Check `EC2_HOST` is correct
- Verify `EC2_SSH_KEY` is the full private key
- Ensure EC2 security group allows SSH (port 22)

### Tests Fail: "OpenAI API key not found"

**Solution:**
- Add `OPENAI_API_KEY` to GitHub Secrets
- Or mock OpenAI calls in tests

---

## ✅ Success Checklist

After setup:

- [ ] GitHub repository created
- [ ] All secrets configured
- [ ] Workflow permissions enabled
- [ ] First push triggers CI/CD
- [ ] Tests pass
- [ ] Docker images built and pushed
- [ ] Can view images in Packages tab
- [ ] Deployment successful (if configured)
- [ ] Services accessible after deployment

---

## 📈 Workflow Timings

**Typical execution times:**

| Workflow | Duration |
|----------|----------|
| **Test All Services** | 3-5 minutes |
| **Build (all 9 images)** | 10-15 minutes (parallel) |
| **Deploy to EC2** | 2-3 minutes |
| **Deploy to K8s** | 3-5 minutes |
| **Total (main branch)** | ~20-25 minutes |

**With caching:**
- Tests: 2-3 minutes
- Builds: 5-8 minutes (using cache)

---

## 🎯 Best Practices

### Branch Protection

1. **Settings** → **Branches** → **Add rule**
2. Branch name pattern: `main`
3. Enable:
   - ✅ Require pull request reviews (1+)
   - ✅ Require status checks to pass
   - ✅ Require branches to be up to date
   - ✅ Include administrators

### Semantic Versioning

Use conventional commits:
```bash
git commit -m "feat: add new feature"
git commit -m "fix: resolve bug"
git commit -m "docs: update README"
git commit -m "chore: update dependencies"
```

### Environment Protection

1. **Settings** → **Environments**
2. Add `production` environment
3. Enable:
   - ✅ Required reviewers
   - ✅ Wait timer (optional)

---

## 🔒 Security Tips

1. **Never commit secrets** - Use GitHub Secrets
2. **Rotate keys regularly** - Update secrets every 90 days
3. **Use least privilege** - Give minimal permissions
4. **Enable Dependabot** - Auto-update dependencies
5. **Scan for secrets** - Use git-secrets or similar

---

## 📞 Need Help?

### Check Logs
```bash
# In GitHub Actions tab
# Click on failed workflow
# Click on failed job
# Expand failed step
# Read error message
```

### Test Locally
```bash
# Install act
brew install act

# Run workflow
act -j test-all
```

### Common Issues

| Error | Solution |
|-------|----------|
| "Resource not accessible" | Enable write permissions |
| "denied: installation not allowed" | Add `packages: write` permission |
| "authentication required" | Check GITHUB_TOKEN |
| "SSH connection failed" | Verify EC2_SSH_KEY and host |

---

## 🎉 You're Ready!

Your microservices now have:
- ✅ Automated testing on every push
- ✅ Docker image builds
- ✅ Push to GitHub Container Registry
- ✅ Automated deployment options
- ✅ Slack notifications (optional)
- ✅ Production-ready CI/CD pipeline

**Next:** Push your code and watch the magic happen! 🚀
