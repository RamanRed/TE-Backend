"""
Neo4j schema management for the Ishikawa Knowledge System.
Handles schema creation, validation, and maintenance.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from .connection import Neo4jConnection
from ..utils.logging import get_logger

logger = get_logger(__name__)


class SchemaManager:
    """Manages Neo4j database schema operations."""

    def __init__(self, connection: Neo4jConnection):
        self.connection = connection

    def create_schema(self, schema_file: Optional[str] = None) -> bool:
        """
        Create database schema from Cypher file.

        Args:
            schema_file: Path to schema file, if None uses default

        Returns:
            bool: True if schema creation successful
        """
        if schema_file is None:
            # Use default schema file
            schema_file = Path(__file__).parent.parent.parent / "neo4j_schema.cypher"

        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return False

        try:
            logger.info(f"Creating schema from file: {schema_file}")

            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_content = f.read()

            # Split into individual statements
            statements = self._split_cypher_statements(schema_content)

            logger.info(f"Found {len(statements)} schema statements to execute")

            # Execute each statement
            for i, statement in enumerate(statements, 1):
                if statement.strip():
                    logger.debug(f"Executing statement {i}/{len(statements)}")
                    try:
                        self.connection.execute_write_query(statement)
                        logger.debug(f"Statement {i} executed successfully")
                    except Exception as e:
                        logger.warning(f"Statement {i} failed (may be expected): {e}")
                        # Continue with other statements

            logger.info("Schema creation completed")
            return True

        except Exception as e:
            logger.error(f"Schema creation failed: {e}")
            return False

    def validate_schema(self) -> Dict[str, Any]:
        """
        Validate current database schema against expected structure.

        Returns:
            Dictionary with validation results
        """
        validation_results = {
            "valid": True,
            "issues": [],
            "node_counts": {},
            "constraint_counts": {},
            "index_counts": {},
            "relationship_types": []
        }

        try:
            # Check expected node labels
            expected_labels = {
                "SystemRoot", "Domain",
                "ProblemStatement", "Phase", "SubPhase", "Content"
            }

            # Check expected relationship types
            expected_relationships = {
                "HAS_DOMAIN", "HAS_PS", "BELONGS_TO",
                "HAS_PHASE", "HAS_SUBPHASE", "HAS_CONTENT"
            }

            labels_result = self.connection.execute_query("""
                CALL db.labels() YIELD label
                RETURN collect(label) as labels
            """)

            if labels_result:
                actual_labels = set(labels_result[0]["labels"])
                missing_labels = expected_labels - actual_labels
                extra_labels = actual_labels - expected_labels

                if missing_labels:
                    validation_results["issues"].append(f"Missing labels: {missing_labels}")
                    validation_results["valid"] = False

                if extra_labels:
                    validation_results["issues"].append(f"Extra labels: {extra_labels}")

            # Check expected relationship types
            relationships_result = self.connection.execute_query("""
                CALL db.relationshipTypes() YIELD relationshipType
                RETURN collect(relationshipType) as relationshipTypes
            """)

            if relationships_result:
                actual_relationships = set(relationships_result[0]["relationshipTypes"])
                missing_relationships = expected_relationships - actual_relationships

                if missing_relationships:
                    validation_results["issues"].append(f"Missing relationship types: {missing_relationships}")
                    validation_results["valid"] = False

            # Collect actual relationship types for reporting
            if relationships_result:
                validation_results["relationship_types"] = relationships_result[0]["relationshipTypes"]

            # Check node counts
            for label in expected_labels:
                count_result = self.connection.execute_query(f"""
                    MATCH (n:{label})
                    RETURN count(n) as count
                """)
                count = count_result[0]["count"] if count_result else 0
                validation_results["node_counts"][label] = count

            # Check constraints
            constraints_result = self.connection.execute_query("""
                CALL db.constraints() YIELD name, ownedIndex, labelsOrTypes, properties, ownedIndex
                RETURN collect({
                    name: name,
                    labelsOrTypes: labelsOrTypes,
                    properties: properties
                }) as constraints
            """)

            if constraints_result:
                validation_results["constraint_counts"] = len(constraints_result[0]["constraints"])

            # Check indexes
            indexes_result = self.connection.execute_query("""
                CALL db.indexes() YIELD name, labelsOrTypes, properties, type
                WHERE type <> 'LOOKUP'
                RETURN collect({
                    name: name,
                    labelsOrTypes: labelsOrTypes,
                    properties: properties,
                    type: type
                }) as indexes
            """)

            if indexes_result:
                validation_results["index_counts"] = len(indexes_result[0]["indexes"])

            logger.info(f"Schema validation completed: valid={validation_results['valid']}")
            if validation_results["issues"]:
                logger.warning(f"Schema issues: {validation_results['issues']}")

        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            validation_results["valid"] = False
            validation_results["issues"].append(f"Validation error: {e}")

        return validation_results

    def recreate_indexes(self) -> bool:
        """
        Recreate full-text and other indexes for Neo4j 5.x compatibility.

        Returns:
            bool: True if index recreation successful
        """
        try:
            logger.info("Recreating database indexes")

            # Drop existing indexes if they exist
            drop_queries = [
                "DROP INDEX ps_text_index IF EXISTS",
                "DROP INDEX content_text_index IF EXISTS",
                # legacy index names
                "DROP INDEX record_text_index IF EXISTS",
                "DROP INDEX problem_fulltext IF EXISTS",
                "DROP INDEX cause_fulltext IF EXISTS",
                "DROP INDEX evidence_fulltext IF EXISTS"
            ]

            for query in drop_queries:
                try:
                    self.connection.execute_write_query(query)
                    logger.debug(f"Dropped index: {query}")
                except Exception as e:
                    logger.debug(f"Index drop failed (may not exist): {e}")

            # Create full-text indexes for new PS-centric schema
            create_queries = [
                """
                CREATE FULLTEXT INDEX ps_text_index
                FOR (n:ProblemStatement)
                ON EACH [n.text, n.title, n.keywords, n.ticket_ref, n.part_number]
                """,
                """
                CREATE FULLTEXT INDEX content_text_index
                FOR (n:Content)
                ON EACH [n.text, n.summary, n.keywords, n.root_cause, n.corrective_action]
                """
            ]

            for query in create_queries:
                try:
                    self.connection.execute_write_query(query)
                    logger.debug("Created full-text index")
                except Exception as e:
                    logger.error(f"Failed to create index: {e}")
                    return False

            logger.info("Index recreation completed successfully")
            return True

        except Exception as e:
            logger.error(f"Index recreation failed: {e}")
            return False

    def clear_database(self) -> bool:
        """
        Clear all data from database (use with caution).

        Returns:
            bool: True if database cleared successfully
        """
        try:
            logger.warning("Clearing all database data")

            # Delete all nodes and relationships
            self.connection.execute_write_query("""
                MATCH (n)
                DETACH DELETE n
            """)

            logger.info("Database cleared successfully")
            return True

        except Exception as e:
            logger.error(f"Database clear failed: {e}")
            return False

    def get_schema_info(self) -> Dict[str, Any]:
        """
        Get comprehensive schema information.

        Returns:
            Dictionary with schema details
        """
        schema_info = {
            "labels": [],
            "relationship_types": [],
            "constraints": [],
            "indexes": [],
            "node_counts": {}
        }

        try:
            # Get labels
            labels_result = self.connection.execute_query("""
                CALL db.labels() YIELD label
                RETURN collect(label) as labels
            """)
            if labels_result:
                schema_info["labels"] = labels_result[0]["labels"]

            # Get relationship types
            rel_result = self.connection.execute_query("""
                CALL db.relationshipTypes() YIELD relationshipType
                RETURN collect(relationshipType) as relationshipTypes
            """)
            if rel_result:
                schema_info["relationship_types"] = rel_result[0]["relationshipTypes"]

            # Get constraints
            constraints_result = self.connection.execute_query("""
                CALL db.constraints() YIELD name, labelsOrTypes, properties, ownedIndex
                RETURN collect({
                    name: name,
                    labelsOrTypes: labelsOrTypes,
                    properties: properties,
                    ownedIndex: ownedIndex
                }) as constraints
            """)
            if constraints_result:
                schema_info["constraints"] = constraints_result[0]["constraints"]

            # Get indexes
            indexes_result = self.connection.execute_query("""
                CALL db.indexes() YIELD name, labelsOrTypes, properties, type
                RETURN collect({
                    name: name,
                    labelsOrTypes: labelsOrTypes,
                    properties: properties,
                    type: type
                }) as indexes
            """)
            if indexes_result:
                schema_info["indexes"] = indexes_result[0]["indexes"]

            # Get node counts for each label
            for label in schema_info["labels"]:
                count_result = self.connection.execute_query(f"""
                    MATCH (n:{label})
                    RETURN count(n) as count
                """)
                count = count_result[0]["count"] if count_result else 0
                schema_info["node_counts"][label] = count

        except Exception as e:
            logger.error(f"Failed to get schema info: {e}")

        return schema_info

    def _split_cypher_statements(self, content: str) -> List[str]:
        """
        Split Cypher content into individual statements.

        Args:
            content: Raw Cypher content

        Returns:
            List of individual Cypher statements
        """
        statements = []
        current_statement = []
        in_multiline_comment = False

        for line in content.split('\n'):
            line = line.strip()

            # Handle multiline comments
            if line.startswith('/*'):
                in_multiline_comment = True
            if in_multiline_comment:
                if '*/' in line:
                    in_multiline_comment = False
                continue

            # Skip single-line comments and empty lines
            if line.startswith('//') or line.startswith('--') or not line:
                continue

            current_statement.append(line)

            # Check for statement end
            if line.endswith(';'):
                statement = ' '.join(current_statement)
                statements.append(statement)
                current_statement = []

        # Add any remaining statement
        if current_statement:
            statement = ' '.join(current_statement)
            if statement.strip():
                statements.append(statement)

        return statements