"""
Neo4j database connection and session management.
Provides connection pooling, session handling, and transaction management.
"""

import logging
from contextlib import contextmanager
from typing import Optional, Generator, Any
from neo4j import GraphDatabase, Driver, Session
from neo4j.exceptions import ServiceUnavailable, AuthError

from ..utils.config import DatabaseConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


class Neo4jConnection:
    """Manages Neo4j database connections and sessions."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._driver: Optional[Driver] = None
        self._connected = False

    def connect(self) -> bool:
        """
        Establish connection to Neo4j database.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            logger.info(f"Connecting to Neo4j at {self.config.host}:{self.config.port}")

            self._driver = GraphDatabase.driver(
                uri=self.config.uri,
                auth=(self.config.username, self.config.password),
                max_connection_lifetime=self.config.max_connection_lifetime,
                max_connection_pool_size=self.config.max_connection_pool_size,
                connection_acquisition_timeout=self.config.connection_acquisition_timeout
            )

            # Test connection — use named database if specified (required for Neo4j Aura)
            db_kwargs = {"database": self.config.database} if self.config.database else {}
            with self._driver.session(**db_kwargs) as session:
                result = session.run("RETURN 'Connection test' as message")
                record = result.single()
                if record and record["message"] == "Connection test":
                    self._connected = True
                    logger.info("Neo4j connection established successfully")
                    return True
                else:
                    logger.error("Connection test failed - unexpected response")
                    return False

        except AuthError as e:
            logger.error(f"Authentication failed: {e}")
            return False
        except ServiceUnavailable as e:
            logger.error(f"Neo4j service unavailable: {e}")
            return False
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Close the database connection."""
        if self._driver:
            self._driver.close()
            self._driver = None
            self._connected = False
            logger.info("Neo4j connection closed")

    def is_connected(self) -> bool:
        """Check if database connection is active with a live ping."""
        if not self._connected or self._driver is None:
            return False
        try:
            db_kwargs = {"database": self.config.database} if self.config.database else {}
            with self._driver.session(**db_kwargs) as _ping_session:
                _ping_session.run("RETURN 1")
            return True
        except Exception:
            self._connected = False
            return False

    @contextmanager
    def session(self, **kwargs) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.

        Yields:
            Session: Neo4j session object

        Raises:
            RuntimeError: If not connected to database
        """
        if not self.is_connected():
            raise RuntimeError("Not connected to Neo4j database")

        db_kwargs = {"database": self.config.database} if self.config.database else {}
        db_kwargs.update(kwargs)
        session = self._driver.session(**db_kwargs)
        try:
            logger.debug("Database session opened")
            yield session
        except Exception as e:
            logger.error(f"Session error: {e}")
            raise
        finally:
            session.close()
            logger.debug("Database session closed")

    def execute_query(
        self,
        query: str,
        parameters: Optional[dict] = None,
        **session_kwargs
    ) -> list:
        """
        Execute a Cypher query and return results.

        Args:
            query: Cypher query string
            parameters: Query parameters
            **session_kwargs: Additional session configuration

        Returns:
            List of query results

        Raises:
            RuntimeError: If query execution fails
        """
        parameters = parameters or {}

        with self.session(**session_kwargs) as session:
            try:
                logger.debug(f"Executing query: {query[:100]}...")
                logger.debug(f"Parameters: {parameters}")

                result = session.run(query, parameters)
                records = [record.data() for record in result]

                logger.debug(f"Query returned {len(records)} records")
                return records

            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                logger.error(f"Query: {query}")
                logger.error(f"Parameters: {parameters}")
                raise RuntimeError(f"Query execution failed: {e}")

    def execute_write_query(
        self,
        query: str,
        parameters: Optional[dict] = None,
        **session_kwargs
    ) -> list:
        """
        Execute a write Cypher query within a transaction.

        Args:
            query: Cypher write query
            parameters: Query parameters
            **session_kwargs: Additional session configuration

        Returns:
            List of query results
        """
        with self.session(**session_kwargs) as session:
            with session.begin_transaction() as tx:
                try:
                    logger.debug(f"Executing write query: {query[:100]}...")
                    result = tx.run(query, parameters or {})
                    records = [record.data() for record in result]
                    tx.commit()

                    logger.debug(f"Write query completed, affected {len(records)} records")
                    return records

                except Exception as e:
                    logger.error(f"Write query failed, rolling back: {e}")
                    tx.rollback()
                    raise RuntimeError(f"Write query failed: {e}")

    def health_check(self) -> dict:
        """
        Perform database health check.

        Returns:
            Dictionary with health status information
        """
        health_info = {
            "connected": self.is_connected(),
            "database_info": None,
            "node_count": 0,
            "relationship_count": 0,
            "status": "unknown"
        }

        if not self.is_connected():
            health_info["status"] = "disconnected"
            return health_info

        try:
            # Get database info
            db_info = self.execute_query(
                "CALL dbms.components() YIELD name, versions, edition "
                "RETURN name, versions[0] AS version, edition LIMIT 1"
            )
            if db_info:
                health_info["database_info"] = db_info[0]

            # Get node count
            node_result = self.execute_query("MATCH (n) RETURN count(n) as node_count")
            if node_result:
                health_info["node_count"] = node_result[0]["node_count"]

            # Get relationship count
            rel_result = self.execute_query("MATCH ()-[r]->() RETURN count(r) as relationship_count")
            if rel_result:
                health_info["relationship_count"] = rel_result[0]["relationship_count"]

            health_info["status"] = "healthy"
            logger.debug(f"Health check passed: {health_info}")

        except Exception as e:
            logger.error(f"Health check failed: {e}")
            health_info["status"] = "error"
            health_info["error"] = str(e)

        return health_info


class DatabaseManager:
    """High-level database manager with connection lifecycle management."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection = Neo4jConnection(config)

    def __enter__(self):
        """Context manager entry - establish connection."""
        if not self.connection.connect():
            raise RuntimeError("Failed to establish database connection")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        self.connection.disconnect()

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self.connection.is_connected()

    def get_connection(self) -> Neo4jConnection:
        """Get the underlying connection object."""
        return self.connection

    def health_check(self) -> dict:
        """Perform database health check."""
        return self.connection.health_check()