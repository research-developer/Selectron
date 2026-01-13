# Sanic Subdomain Routing

This document covers Sanic's subdomain routing capabilities and patterns for implementing wildcard subdomain handling in Selectron's Page Object Model server.

## Native Host Parameter

Sanic's `@app.route()` decorator accepts a `host` parameter for routing requests based on the HTTP Host header.

### Basic Usage

```python
from sanic import Sanic
from sanic.response import json

app = Sanic("SubdomainApp")

# Route for a specific host
@app.route('/api/data', host='api.example.com')
async def api_handler(request):
    return json({"source": "api subdomain"})

# Route for multiple hosts
@app.route('/status', host=['api.example.com', 'admin.example.com'])
async def status_handler(request):
    return json({"host": request.host})
```

### Limitations

The native `host` parameter has important limitations:

| Feature | Supported |
|---------|-----------|
| Exact host match | Yes |
| Multiple hosts (list) | Yes |
| Wildcard patterns (`*.example.com`) | **No** |
| Regex patterns | **No** |

For wildcard subdomain routing, a middleware-based approach is required.

---

## Middleware-Based Wildcard Solution

Since Sanic does not support wildcard host patterns natively, middleware provides the solution for dynamic subdomain extraction.

### Subdomain Extraction Middleware

```python
from sanic import Sanic
from sanic.response import json

app = Sanic("WildcardSubdomain")

@app.middleware("request")
async def extract_subdomain(request):
    """
    Extract subdomain from the Host header.

    Examples:
        - claude.pom.localhost:8000 -> subdomain = "claude"
        - obsidian.pom.localhost:8000 -> subdomain = "obsidian"
        - pom.localhost:8000 -> subdomain = None
    """
    host = request.host.split(":")[0]  # Remove port number
    parts = host.split(".")

    if len(parts) >= 3:  # e.g., claude.pom.localhost
        request.ctx.subdomain = parts[0]
    else:
        request.ctx.subdomain = None

@app.route('/resource')
async def handle_resource(request):
    subdomain = request.ctx.subdomain
    if subdomain:
        return json({"app": subdomain, "status": "ok"})
    return json({"error": "No subdomain specified"}, status=400)
```

### How It Works

1. **Request arrives** with Host header (e.g., `claude.pom.localhost:8000`)
2. **Middleware executes** before route handlers
3. **Port is stripped** using `split(":")[0]`
4. **Host is split** into parts: `["claude", "pom", "localhost"]`
5. **Subdomain is extracted** and stored in `request.ctx`
6. **Route handlers access** subdomain via `request.ctx.subdomain`

---

## Design Pattern: Dynamic Module Loading

The MicroManager pattern demonstrates dynamic service loading based on URL components. This pattern applies directly to Selectron's POM architecture.

### MicroManager Implementation

Located at `/Users/preston/Projects/MicroManager/main.py`:

```python
from sanic import Sanic
from sanic.response import json
import importlib
import sys

app = Sanic("MicroManager")

@app.middleware("request")
async def extract_subdomain(request):
    host = request.host.split(":")[0]
    parts = host.split(".")
    if len(parts) >= 3:
        request.ctx.subdomain = parts[0]
    else:
        request.ctx.subdomain = None

@app.route('/srv/<function>')
async def handle_request(request, function):
    """
    Dynamic service routing.

    URL: /srv/get_element
    Subdomain: claude
    -> Loads services/claude/service.py
    -> Calls service.get_element(request)
    """
    module = request.ctx.subdomain

    if not module:
        return json({"error": "Subdomain required"}, status=400)

    try:
        # Dynamic import of service module
        service_path = f"services.{module}.service"
        if service_path in sys.modules:
            service_module = importlib.reload(sys.modules[service_path])
        else:
            service_module = importlib.import_module(service_path)

        # Get and call the function
        handler = getattr(service_module, function)
        result = await handler(request)
        return json(result)

    except ModuleNotFoundError:
        return json({"error": f"Service '{module}' not found"}, status=404)
    except AttributeError:
        return json({"error": f"Function '{function}' not found"}, status=404)
```

### Directory Structure

```
services/
    claude/
        service.py      # Claude-specific handlers
    obsidian/
        service.py      # Obsidian-specific handlers
    cursor/
        service.py      # Cursor-specific handlers
```

---

## Application to Selectron POMs

Selectron's Page Object Model server uses subdomains to identify target applications and paths following the WebSpec convention.

### URL Structure

```
{subdomain}.pom.localhost/{root}/{collection}/{id}{.format}
```

| Component | Description | Examples |
|-----------|-------------|----------|
| `subdomain` | Target application | `claude`, `obsidian`, `cursor` |
| `root` | Resource category | `/pom/`, `/dom/`, `/orm/`, `/llm/`, `/wim/` |
| `collection` | Element collection | `buttons`, `inputs`, `panels` |
| `id` | Specific element | `submit`, `search-field` |
| `.format` | Response format | `.json`, `.html`, `.xml` |

### Example URLs

```
claude.pom.localhost/pom/buttons/submit.json
obsidian.pom.localhost/dom/panels/sidebar.html
cursor.pom.localhost/orm/models/file-tree.json
```

### Selectron Router Implementation

```python
from sanic import Sanic
from sanic.response import json, html
from pathlib import Path
import importlib

app = Sanic("SelectronPOM")

# Root categories
ROOTS = {"pom", "dom", "orm", "llm", "wim"}

@app.middleware("request")
async def extract_context(request):
    """Extract subdomain (app) and parse format from path."""
    # Extract subdomain
    host = request.host.split(":")[0]
    parts = host.split(".")
    request.ctx.app = parts[0] if len(parts) >= 3 else None

    # Extract format from path extension
    path = request.path
    if "." in path.split("/")[-1]:
        request.ctx.format = path.rsplit(".", 1)[1]
        request.ctx.clean_path = path.rsplit(".", 1)[0]
    else:
        request.ctx.format = "json"  # Default format
        request.ctx.clean_path = path

@app.route('/<root>/<collection>/<element_id>')
@app.route('/<root>/<collection>/<element_id>.<fmt>')
async def get_element(request, root, collection, element_id, fmt=None):
    """
    Retrieve a Page Object Model element.

    Example: GET claude.pom.localhost/pom/buttons/submit.json
    """
    app_name = request.ctx.app
    response_format = fmt or request.ctx.format

    if root not in ROOTS:
        return json({"error": f"Invalid root: {root}"}, status=400)

    if not app_name:
        return json({"error": "Subdomain required"}, status=400)

    # Load POM for the application
    pom_path = Path(f"poms/{app_name}/{root}/{collection}.json")

    if not pom_path.exists():
        return json({
            "error": f"Collection '{collection}' not found for {app_name}"
        }, status=404)

    # Load and return element
    import json as json_lib
    pom_data = json_lib.loads(pom_path.read_text())

    if element_id not in pom_data:
        return json({
            "error": f"Element '{element_id}' not found in {collection}"
        }, status=404)

    element = pom_data[element_id]

    # Format response
    if response_format == "json":
        return json(element)
    elif response_format == "html":
        return html(f"<pre>{json_lib.dumps(element, indent=2)}</pre>")
    else:
        return json(element)


@app.route('/<root>/<collection>')
async def list_collection(request, root, collection):
    """List all elements in a collection."""
    app_name = request.ctx.app

    if root not in ROOTS:
        return json({"error": f"Invalid root: {root}"}, status=400)

    pom_path = Path(f"poms/{app_name}/{root}/{collection}.json")

    if not pom_path.exists():
        return json({"elements": []})

    import json as json_lib
    pom_data = json_lib.loads(pom_path.read_text())

    return json({
        "app": app_name,
        "root": root,
        "collection": collection,
        "elements": list(pom_data.keys())
    })
```

---

## Local Development Setup

For local development, configure DNS to resolve wildcard subdomains to localhost.

### Option 1: /etc/hosts (Limited)

```bash
# /etc/hosts - Must add each subdomain explicitly
127.0.0.1  claude.pom.localhost
127.0.0.1  obsidian.pom.localhost
127.0.0.1  cursor.pom.localhost
```

### Option 2: dnsmasq (Recommended)

```bash
# Install dnsmasq
brew install dnsmasq

# Configure wildcard
echo 'address=/.pom.localhost/127.0.0.1' >> /opt/homebrew/etc/dnsmasq.conf

# Start service
sudo brew services start dnsmasq

# Configure macOS to use dnsmasq for .localhost
sudo mkdir -p /etc/resolver
echo 'nameserver 127.0.0.1' | sudo tee /etc/resolver/localhost
```

### Option 3: Header Override (Development Only)

For quick testing without DNS changes:

```python
@app.middleware("request")
async def extract_subdomain(request):
    # Allow header override for development
    if "X-Subdomain" in request.headers:
        request.ctx.subdomain = request.headers["X-Subdomain"]
        return

    # Standard extraction
    host = request.host.split(":")[0]
    parts = host.split(".")
    request.ctx.subdomain = parts[0] if len(parts) >= 3 else None
```

Usage:
```bash
curl -H "X-Subdomain: claude" http://localhost:8000/pom/buttons/submit.json
```

---

## Summary

| Approach | Use Case | Wildcard Support |
|----------|----------|------------------|
| Native `host` parameter | Fixed, known hosts | No |
| Request middleware | Dynamic subdomains | Yes |
| Dynamic module loading | Service routing | Yes |

The middleware-based approach provides the flexibility needed for Selectron's multi-application POM server, enabling wildcard subdomain routing while maintaining clean, RESTful URL patterns.
