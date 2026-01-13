"""
Selectron Server Routes

Blueprint modules for each path root:
- pom: Page Object Model definitions and operations
- dom: Direct DOM/WebDriver element interactions
- orm: Object-Relational Mapping for data bindings
- llm: AI/LLM assistance for element discovery
- wim: Window Interface Manager for app control
"""

from .pom import pom_bp
from .dom import dom_bp
from .wim import wim_bp

__all__ = ["pom_bp", "dom_bp", "wim_bp"]
