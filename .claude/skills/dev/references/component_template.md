# Component Template

Use this template when creating a new module or class in ContextCrawler. It has all the standard boilerplate pre-filled.

## Module Template

```python
"""
contextcrawler.<package>.<module> — <One-line description>.

<Longer description of what this module does, when to use it, and how it
fits into the broader crawl pipeline.>
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class <ModelName>(BaseModel):
    """<Description of what this model represents>."""

    # Add fields here
    pass


# ---------------------------------------------------------------------------
# Core Implementation
# ---------------------------------------------------------------------------

class <ClassName>:
    """<Description of what this class does>.

    Args:
        config: Crawler configuration.
        <other_dep>: <Description>.

    Example::

        async with <ClassName>(config=config) as instance:
            result = await instance.process(input_data)
    """

    def __init__(
        self,
        config: "CrawlerConfig",
        *,
        # Add injected dependencies here
    ) -> None:
        self.config = config
        self._initialized = False

    async def __aenter__(self) -> "<ClassName>":
        await self._setup()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self._teardown()

    async def _setup(self) -> None:
        """Initialize resources (connections, caches, etc.)."""
        self._initialized = True
        logger.debug("%s initialized", self.__class__.__name__)

    async def _teardown(self) -> None:
        """Clean up resources."""
        self._initialized = False
        logger.debug("%s torn down", self.__class__.__name__)

    # ---- Public API -------------------------------------------------------

    async def process(self, data: Any) -> Any:
        """<Describe what this method does>.

        Args:
            data: <Description>.

        Returns:
            <Description of return value>.

        Raises:
            ContextCrawlerError: If <condition>.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Factory (optional — use if construction is complex)
# ---------------------------------------------------------------------------

def create_<component>(config: "CrawlerConfig", **kwargs: Any) -> <ClassName>:
    """Create a configured <ClassName> instance.

    This factory handles wiring up dependencies and applying config defaults.
    """
    return <ClassName>(config=config, **kwargs)
```

## Test Template

```python
"""Tests for contextcrawler.<package>.<module>."""

import asyncio

import pytest

from contextcrawler.<package>.<module> import <ClassName>, <ModelName>


@pytest.fixture
def config():
    """Create a test configuration."""
    from contextcrawler.core.config import CrawlerConfig
    return CrawlerConfig(
        max_concurrent_requests=2,
        request_delay=0,
    )


@pytest.fixture
async def instance(config):
    """Create and initialize a <ClassName> for testing."""
    async with <ClassName>(config=config) as inst:
        yield inst


class TestModelName:
    """Tests for the <ModelName> data model."""

    def test_creation_with_defaults(self):
        model = <ModelName>()
        # assert model.field == expected

    def test_validation_rejects_bad_input(self):
        with pytest.raises(ValueError):
            <ModelName>(bad_field="invalid")


class Test<ClassName>:
    """Tests for <ClassName>."""

    @pytest.mark.asyncio
    async def test_process_happy_path(self, instance):
        result = await instance.process(valid_input)
        assert result == expected_output

    @pytest.mark.asyncio
    async def test_process_handles_error(self, instance):
        with pytest.raises(ContextCrawlerError):
            await instance.process(bad_input)
```
