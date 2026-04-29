"""
Database package for the Ishikawa Knowledge System.
Provides Neo4j connectivity, schema management, and data access operations.
"""

from .connection import DatabaseManager, Neo4jConnection
from .query_builder import QueryBuilder
from .repository import KnowledgeRepository
from .schema import SchemaManager
from .search import SearchCriteria

__all__ = [
    # Connection management
    "Neo4jConnection",
    "DatabaseManager",

    # Schema operations
    "SchemaManager",

    # Query building
    "QueryBuilder",
    "SearchCriteria",

    # Data access
    "KnowledgeRepository"
]
