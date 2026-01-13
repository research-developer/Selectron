"""
POM Routes - Page Object Model Endpoints

Provides REST endpoints for accessing and manipulating Page Object Model
definitions. This is the core of the Selectron API.

Endpoints:
    GET  /pom/elements           - List all element definitions
    GET  /pom/elements/{id}      - Get specific element definition
    GET  /pom/operations         - List all operation definitions
    GET  /pom/operations/{id}    - Get specific operation definition
    POST /pom/operations/{id}    - Execute an operation
    GET  /pom/schema             - Get the POM schema for the app
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any

from sanic import Blueprint, Request
from sanic.response import json as json_response
from sanic.exceptions import NotFound, BadRequest

from ..config import get_server_config
from ..middleware.subdomain import get_app_from_request
from ..middleware.format_negotiation import negotiate_format, strip_format_suffix


# Create blueprint with /pom prefix
pom_bp = Blueprint("pom", url_prefix="/pom")


def load_json_file(path: Path) -> Optional[Dict[str, Any]]:
    """Load and parse a JSON file, returning None if not found."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise BadRequest(f"Invalid JSON in {path.name}: {e}")


def get_pom_data(app_name: str, collection: str) -> Dict[str, Any]:
    """
    Load POM data for an app and collection.

    Args:
        app_name: Application name (from subdomain)
        collection: Collection name (elements, operations, etc.)

    Returns:
        Parsed JSON data with items converted to dict keyed by 'id'

    Raises:
        NotFound: If the POM file doesn't exist
    """
    config = get_server_config()
    pom_path = config.get_element_path(app_name, collection)

    data = load_json_file(pom_path)
    if data is None:
        raise NotFound(f"No {collection} defined for app '{app_name}'")

    return data


def get_items_as_dict(data: Dict[str, Any], key: str = "elements") -> Dict[str, Any]:
    """
    Convert a list of items with 'id' fields to a dict keyed by id.

    The POM JSON files store items as arrays with 'id' fields.
    This converts them to dicts for easy lookup.

    Args:
        data: Raw POM data with items in a list
        key: Key containing the items list (e.g., "elements", "operations")

    Returns:
        Dict mapping item IDs to their data
    """
    items = data.get(key, [])
    if isinstance(items, list):
        return {item["id"]: item for item in items if "id" in item}
    elif isinstance(items, dict):
        return items
    return {}


# ============================================================================
# Elements Endpoints
# ============================================================================

@pom_bp.get("/elements")
async def list_elements(request: Request):
    """
    List all element definitions for the app.

    Returns:
        JSON object with element names and basic info
    """
    app = get_app_from_request(request)
    data = get_pom_data(app, "elements")
    elements = get_items_as_dict(data, "elements")

    # Return summary of each element
    summary = {}
    for name, elem in elements.items():
        selector = elem.get("selector", {})
        summary[name] = {
            "selector": selector.get("value") if isinstance(selector, dict) else selector,
            "selector_type": selector.get("type", "css") if isinstance(selector, dict) else "css",
            "component_type": elem.get("component_type"),
            "crud_type": elem.get("crud_type"),
        }

    return json_response({
        "app": app,
        "collection": "elements",
        "count": len(summary),
        "elements": summary,
    })


@pom_bp.get("/elements/<element_id>")
async def get_element(request: Request, element_id: str):
    """
    Get a specific element definition.

    Args:
        element_id: Element identifier (may include .json suffix)

    Returns:
        Full element definition
    """
    app = get_app_from_request(request)
    data = get_pom_data(app, "elements")
    elements = get_items_as_dict(data, "elements")

    # Strip format suffix if present (e.g., btn.json -> btn)
    element_id, fmt = strip_format_suffix(element_id)
    if fmt:
        request.ctx.format = fmt

    if element_id not in elements:
        raise NotFound(f"Element '{element_id}' not found in app '{app}'")

    element = elements[element_id]

    return json_response({
        "app": app,
        "id": element_id,
        "element": element,
    })


# ============================================================================
# Operations Endpoints
# ============================================================================

@pom_bp.get("/operations")
async def list_operations(request: Request):
    """
    List all operation definitions for the app.

    Returns:
        JSON object with operation names and basic info
    """
    app = get_app_from_request(request)
    data = get_pom_data(app, "operations")
    operations = get_items_as_dict(data, "operations")

    # Return summary of each operation
    summary = {}
    for name, op in operations.items():
        summary[name] = {
            "description": op.get("description"),
            "steps": len(op.get("steps", [])),
            "parameters": list(op.get("parameters", {}).keys()) if isinstance(op.get("parameters"), dict) else [],
        }

    return json_response({
        "app": app,
        "collection": "operations",
        "count": len(summary),
        "operations": summary,
    })


@pom_bp.get("/operations/<operation_id>")
async def get_operation(request: Request, operation_id: str):
    """
    Get a specific operation definition.

    Args:
        operation_id: Operation identifier (may include .json suffix)

    Returns:
        Full operation definition
    """
    app = get_app_from_request(request)
    data = get_pom_data(app, "operations")
    operations = get_items_as_dict(data, "operations")

    # Strip format suffix if present
    operation_id, fmt = strip_format_suffix(operation_id)
    if fmt:
        request.ctx.format = fmt

    if operation_id not in operations:
        raise NotFound(f"Operation '{operation_id}' not found in app '{app}'")

    operation = operations[operation_id]

    return json_response({
        "app": app,
        "id": operation_id,
        "operation": operation,
    })


@pom_bp.post("/operations/<operation_id>")
async def execute_operation(request: Request, operation_id: str):
    """
    Execute an operation.

    This is a placeholder - actual execution requires integration with
    the Selectron driver and session management.

    Args:
        operation_id: Operation to execute (may include .json suffix)

    Request Body:
        JSON with operation parameters

    Returns:
        Execution result
    """
    app = get_app_from_request(request)
    data = get_pom_data(app, "operations")
    operations = get_items_as_dict(data, "operations")

    # Strip format suffix if present
    operation_id, fmt = strip_format_suffix(operation_id)
    if fmt:
        request.ctx.format = fmt

    if operation_id not in operations:
        raise NotFound(f"Operation '{operation_id}' not found in app '{app}'")

    operation = operations[operation_id]
    params = request.json or {}

    # TODO: Integrate with Selectron driver for actual execution
    # For now, return the operation that would be executed

    return json_response({
        "app": app,
        "operation": operation_id,
        "status": "queued",
        "message": "Operation execution not yet implemented",
        "would_execute": {
            "operation": operation,
            "parameters": params,
        }
    })


# ============================================================================
# Schema Endpoints
# ============================================================================

@pom_bp.get("/schema")
async def get_schema(request: Request):
    """
    Get the full POM schema for an app.

    Returns all elements, operations, and metadata.
    """
    app = get_app_from_request(request)
    config = get_server_config()
    app_path = config.get_pom_path(app)

    if not app_path.exists():
        raise NotFound(f"No POM defined for app '{app}'")

    schema = {
        "app": app,
        "path": str(app_path),
        "collections": {},
    }

    # Load all JSON files in the app directory
    for json_file in app_path.glob("*.json"):
        collection_name = json_file.stem
        data = load_json_file(json_file)
        if data:
            schema["collections"][collection_name] = {
                "count": len(data),
                "keys": list(data.keys()),
            }

    return json_response(schema)


@pom_bp.get("/<collection>")
async def list_collection(request: Request, collection: str):
    """
    Generic collection listing endpoint.

    Handles any collection beyond elements/operations.
    """
    app = get_app_from_request(request)

    try:
        data = get_pom_data(app, collection)
    except NotFound:
        raise NotFound(f"Collection '{collection}' not found for app '{app}'")

    return json_response({
        "app": app,
        "collection": collection,
        "count": len(data),
        "keys": list(data.keys()),
    })


@pom_bp.get("/<collection>/<item_id>")
async def get_collection_item(request: Request, collection: str, item_id: str):
    """
    Generic collection item endpoint.

    Handles any item in any collection.
    """
    app = get_app_from_request(request)

    # Strip format suffix if present
    item_id, fmt = strip_format_suffix(item_id)
    if fmt:
        request.ctx.format = fmt

    try:
        data = get_pom_data(app, collection)
    except NotFound:
        raise NotFound(f"Collection '{collection}' not found for app '{app}'")

    if item_id not in data:
        raise NotFound(f"Item '{item_id}' not found in {collection} for app '{app}'")

    return json_response({
        "app": app,
        "collection": collection,
        "id": item_id,
        "data": data[item_id],
    })
