"""Neo4j graph database connection manager.

Provides a ``GraphDB`` class with connection pooling, retry logic, and
graceful degradation when Neo4j is unavailable. All graph-related modules
use this single entry point to interact with the database.

Configuration via environment variables:
    NEO4J_URI:      bolt://localhost:7687  (default)
    NEO4J_USER:     neo4j                  (default)
    NEO4J_PASSWORD: nfl_graph_2026         (default)
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import (
        AuthError,
        ServiceUnavailable,
        SessionExpired,
        TransientError,
    )

    _NEO4J_AVAILABLE = True
except ImportError:
    _NEO4J_AVAILABLE = False

# Defaults match docker-compose.yml
_DEFAULT_URI = "bolt://localhost:7687"
_DEFAULT_USER = "neo4j"
_DEFAULT_PASSWORD = "nfl_graph_2026"

# Retry configuration
_MAX_RETRIES = 3


class GraphDB:
    """Neo4j connection manager with retry logic and schema bootstrapping.

    Usage::

        with GraphDB() as gdb:
            gdb.run("MATCH (n) RETURN count(n) AS cnt")

    If Neo4j is not reachable the context manager still succeeds but
    ``is_connected`` returns False and ``run`` returns an empty list.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._uri = uri or os.getenv("NEO4J_URI", _DEFAULT_URI)
        self._user = user or os.getenv("NEO4J_USER", _DEFAULT_USER)
        self._password = password or os.getenv("NEO4J_PASSWORD", _DEFAULT_PASSWORD)
        self._driver = None  # type: ignore[assignment]
        self._connected = False

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "GraphDB":
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection to Neo4j, silently degrading on failure."""
        if not _NEO4J_AVAILABLE:
            logger.warning(
                "neo4j Python driver not installed — graph features disabled"
            )
            return

        try:
            self._driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
                max_connection_lifetime=3600,
                connection_acquisition_timeout=10,
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            self._connected = True
            logger.info("Connected to Neo4j at %s", self._uri)
        except (ServiceUnavailable, AuthError, OSError) as exc:
            logger.warning("Neo4j unavailable (%s) — graph features disabled", exc)
            self._connected = False
        except Exception as exc:
            logger.warning(
                "Unexpected error connecting to Neo4j (%s) — graph features disabled",
                exc,
            )
            self._connected = False

    def close(self) -> None:
        """Close the driver connection if open."""
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Return True if an active connection exists."""
        return self._connected

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def run(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a Cypher query with automatic retry on transient errors.

        Args:
            cypher: Cypher query string.
            parameters: Query parameters dict.
            database: Target database name (None = default).

        Returns:
            List of record dicts. Empty list if Neo4j is unavailable.
        """
        if not self._connected or self._driver is None:
            return []

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with self._driver.session(database=database) as session:
                    result = session.run(cypher, parameters or {})
                    return [dict(record) for record in result]
            except (TransientError, SessionExpired) as exc:
                last_exc = exc
                logger.warning(
                    "Transient Neo4j error (attempt %d/%d): %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
            except ServiceUnavailable as exc:
                logger.warning("Neo4j service unavailable: %s", exc)
                self._connected = False
                return []
            except Exception as exc:
                logger.error("Neo4j query failed: %s", exc)
                return []

        logger.error("Neo4j query failed after %d retries: %s", _MAX_RETRIES, last_exc)
        return []

    def run_write(
        self,
        cypher: str,
        parameters: Optional[Dict[str, Any]] = None,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a write transaction with automatic retry.

        Args:
            cypher: Cypher write query.
            parameters: Query parameters dict.
            database: Target database name.

        Returns:
            List of record dicts. Empty list if Neo4j is unavailable.
        """
        if not self._connected or self._driver is None:
            return []

        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                with self._driver.session(database=database) as session:
                    result = session.execute_write(
                        lambda tx: list(tx.run(cypher, parameters or {}))
                    )
                    return [dict(record) for record in result]
            except (TransientError, SessionExpired) as exc:
                last_exc = exc
                logger.warning(
                    "Transient Neo4j write error (attempt %d/%d): %s",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                )
            except ServiceUnavailable as exc:
                logger.warning("Neo4j service unavailable: %s", exc)
                self._connected = False
                return []
            except Exception as exc:
                logger.error("Neo4j write query failed: %s", exc)
                return []

        logger.error("Neo4j write failed after %d retries: %s", _MAX_RETRIES, last_exc)
        return []

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        """Create indexes and constraints for the NFL graph schema.

        Safe to call repeatedly — uses CREATE ... IF NOT EXISTS.
        """
        if not self._connected:
            logger.warning("Skipping schema creation — Neo4j not connected")
            return

        constraints = [
            "CREATE CONSTRAINT player_id IF NOT EXISTS FOR (p:Player) REQUIRE p.gsis_id IS UNIQUE",
            "CREATE CONSTRAINT team_abbr IF NOT EXISTS FOR (t:Team) REQUIRE t.abbr IS UNIQUE",
            "CREATE CONSTRAINT game_id IF NOT EXISTS FOR (g:Game) REQUIRE g.game_id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX player_name IF NOT EXISTS FOR (p:Player) ON (p.name)",
            "CREATE INDEX player_position IF NOT EXISTS FOR (p:Player) ON (p.position)",
            "CREATE INDEX game_season_week IF NOT EXISTS FOR (g:Game) ON (g.season, g.week)",
        ]

        for stmt in constraints + indexes:
            self.run_write(stmt)

        logger.info("Graph schema ensured (constraints + indexes)")
