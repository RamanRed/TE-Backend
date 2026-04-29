"""High-level knowledge repository composed from focused mixins."""

from __future__ import annotations

from .connection import Neo4jConnection
from .query_builder import QueryBuilder
from .repository_search import KnowledgeRepositorySearchMixin
from .repository_write import KnowledgeRepositoryWriteMixin


class KnowledgeRepository(KnowledgeRepositoryWriteMixin, KnowledgeRepositorySearchMixin):
    """Repository for knowledge base operations."""

    def __init__(self, connection: Neo4jConnection):
        self.connection = connection
        self.query_builder = QueryBuilder()
