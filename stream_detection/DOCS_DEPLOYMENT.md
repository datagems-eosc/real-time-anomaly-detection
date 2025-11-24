# Documentation Deployment Guide

This guide explains how to build and deploy the MkDocs documentation.

## Prerequisites

```bash
# Install MkDocs and dependencies
pip install -r docs_requirements.txt
```

## Local Development

### Start Development Server

```bash
# From the stream_detection directory
mkdocs serve

# Or specify custom port
mkdocs serve --dev-addr=127.0.0.1:8001
```

Then open http://127.0.0.1:8000 in your browser.

**Live Reload**: The server automatically reloads when you edit markdown files.

### Build Documentation

```bash
# Build static HTML files
mkdocs build

# Output will be in: site/
```

## Deployment Options

### Option 1: GitHub Pages (Recommended)

#### Manual Deployment

```bash
# Build and deploy to gh-pages branch
mkdocs gh-deploy

# With custom message
mkdocs gh-deploy --message "Update documentation"
```

The documentation will be available at:
`https://datagems-eosc.github.io/real-time-anomaly-detection/`

#### Automatic Deployment (GitHub Actions)

Create `.github/workflows/docs.yml`:

```yaml
name: Deploy Documentation

on:
  push:
    branches:
      - main
    paths:
      - 'stream_detection/docs/**'
      - 'stream_detection/mkdocs.yml'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r stream_detection/docs_requirements.txt
      
      - name: Deploy to GitHub Pages
        run: |
          cd stream_detection
          mkdocs gh-deploy --force
```

### Option 2: Read the Docs

1. Create account at https://readthedocs.org
2. Import project from GitHub
3. Configure:
   - Build process: MkDocs
   - Requirements file: `docs_requirements.txt`
4. Webhook will auto-deploy on push

### Option 3: Self-Hosted

#### Using Docker

```bash
# Build documentation
mkdocs build

# Serve with nginx
docker run -d -p 80:80 \
  -v $(pwd)/site:/usr/share/nginx/html:ro \
  nginx:alpine
```

#### Using Python HTTP Server

```bash
mkdocs build
cd site
python3 -m http.server 8000
```

### Option 4: Static Site Hosting

Deploy the `site/` directory to any static hosting:

- **Netlify**: Drag & drop `site/` folder
- **Vercel**: Import repository, set build command to `mkdocs build`
- **AWS S3**: `aws s3 sync site/ s3://your-bucket --acl public-read`
- **Azure Static Web Apps**: Connect repository

## Documentation Structure

```
docs/
├── index.md                    # Homepage
├── overview/
│   ├── features.md
│   └── how-it-works.md
├── system/
│   ├── architecture.md
│   ├── detection-methods.md
│   └── station-network.md
├── api/
│   ├── overview.md
│   ├── parameters.md
│   ├── response.md
│   └── examples.md
├── setup/
│   ├── installation.md
│   ├── configuration.md
│   ├── deployment.md
│   └── database.md
├── examples/
│   ├── weather-event.md
│   └── device-failure.md
├── faq.md
├── license.md
├── assets/                     # Images, logos
└── stylesheets/
    └── extra.css               # Custom CSS
```

## Customization

### Edit Navigation

Edit `mkdocs.yml`:

```yaml
nav:
  - Overview:
    - Introduction: index.md
    - Key Features: overview/features.md
  - API:
    - Overview: api/overview.md
  # Add more sections here
```

### Change Theme Colors

Edit `mkdocs.yml`:

```yaml
theme:
  palette:
    primary: blue      # Change to: red, pink, purple, etc.
    accent: light blue
```

### Add Custom CSS

1. Create `docs/stylesheets/extra.css`
2. Reference in `mkdocs.yml`:

```yaml
extra_css:
  - stylesheets/extra.css
```

### Add Logo

1. Add logo to `docs/assets/logo.png`
2. Update `mkdocs.yml`:

```yaml
theme:
  logo: assets/logo.png
  favicon: assets/favicon.ico
```

## Versioning

### Using Mike (Multi-Version Docs)

```bash
# Install mike
pip install mike

# Deploy version 1.0
mike deploy 1.0 latest --update-aliases

# Deploy version 2.0
mike deploy 2.0 latest --update-aliases

# Set default version
mike set-default latest

# List versions
mike list
```

Access versions at:
- `/` or `/latest/` - Latest version
- `/1.0/` - Version 1.0
- `/2.0/` - Version 2.0

## Maintenance

### Update Dependencies

```bash
pip install --upgrade -r docs_requirements.txt
```

### Check for Broken Links

```bash
# Install linkchecker
pip install linkchecker

# Build docs
mkdocs build

# Check links
linkchecker site/
```

### Search Optimization

MkDocs Material includes built-in search. To improve it:

1. Use clear headings
2. Include keywords in first paragraphs
3. Use descriptive anchor text for links

## Troubleshooting

### Issue: `mkdocs: command not found`

```bash
# Ensure it's installed
pip install mkdocs

# Or use full path
python3 -m mkdocs serve
```

### Issue: Mermaid diagrams not rendering

```bash
# Install plugin
pip install mkdocs-mermaid2-plugin

# Verify in mkdocs.yml
plugins:
  - mermaid2
```

### Issue: Changes not reflected

```bash
# Clear cache
rm -rf site/
mkdocs build
```

### Issue: GitHub Pages 404

1. Check repository settings → Pages
2. Ensure source is set to `gh-pages` branch
3. Wait 5-10 minutes for deployment
4. Check `https://username.github.io/repo-name/`

## CI/CD Integration

### GitLab CI

```yaml
# .gitlab-ci.yml
pages:
  stage: deploy
  image: python:3.10
  script:
    - pip install -r docs_requirements.txt
    - mkdocs build --site-dir public
  artifacts:
    paths:
      - public
  only:
    - main
```

### Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Build Docs') {
            steps {
                sh 'pip install -r docs_requirements.txt'
                sh 'mkdocs build'
            }
        }
        stage('Deploy') {
            steps {
                sh 'mkdocs gh-deploy'
            }
        }
    }
}
```

## Additional Resources

- **MkDocs**: https://www.mkdocs.org
- **Material Theme**: https://squidfunk.github.io/mkdocs-material/
- **Mermaid Plugin**: https://github.com/fralau/mkdocs-mermaid2-plugin
- **Mike (Versioning)**: https://github.com/jimporter/mike

## Support

For issues with documentation:

1. Check this guide
2. Review MkDocs Material docs
3. Open GitHub issue
4. Contact documentation team

---

**Quick Start Summary**:

```bash
# Install
pip install -r docs_requirements.txt

# Develop
mkdocs serve

# Deploy
mkdocs gh-deploy
```

