"""Plugin manifest model."""

from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    """Metadata describing a KITT plugin."""

    name: str
    version: str = "0.1.0"
    plugin_type: str = Field(
        description="Type of plugin: 'engine', 'benchmark', or 'reporter'"
    )
    entry_point: str = Field(
        description="Python module:class entry point, e.g. 'mypackage.engine:MyEngine'"
    )
    description: str = ""
    author: str = ""
    min_kitt_version: str | None = None
    homepage: str | None = None
