import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.utils.config import get_config, load_config
from src.utils.logging import setup_logging, get_logger
from src.database.connection import DatabaseManager
from src.database.schema import SchemaManager

logger = get_logger(__name__)


def setup_database(args: argparse.Namespace) -> bool:
    """Setup and initialize the database."""
    logger.info("Setting up database...")

    try:
        with DatabaseManager(get_config().database) as db_manager:
            schema_manager = SchemaManager(db_manager.get_connection())

            if not schema_manager.create_schema():
                logger.error("Failed to create database schema")
                return False

            if not schema_manager.recreate_indexes():
                logger.error("Failed to recreate database indexes")
                return False

            validation = schema_manager.validate_schema()
            if validation.get("valid", False):
                logger.info("Schema validation passed")
            else:
                logger.warning(f"Schema validation issues: {validation.get('issues', [])}")

            logger.info("Database setup completed successfully")
            return True

    except Exception as e:
        logger.error(f"Database setup failed: {e}", exc_info=True)
        return False


def run_server(args: argparse.Namespace) -> None:
    """Start the FastAPI server."""
    import uvicorn

    logger.info("Starting Ollama server in background...")
    try:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **kwargs
        )
        logger.info("Ollama server start signal sent successfully.")
    except Exception as e:
        logger.warning(f"Could not start Ollama server automatically (it might already be running): {e}")

    logger.info("Starting FastAPI server...")
    config = get_config()
    uvicorn.run(
        "src.api.app:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )


def test_system(args: argparse.Namespace) -> bool:
    """Run system tests."""
    logger.info("Running system tests...")

    try:
        # Test database connection
        with DatabaseManager(get_config().database) as db_manager:
            if db_manager.health_check().get("status") != "healthy":
                logger.error("Database health check failed")
                return False
        logger.info("Database connection test passed")

        # Test LLM service
        from app.llm.client import LLMService
        if not LLMService(get_config().llm).ensure_model_available():
            logger.error("LLM service not available")
            return False
        logger.info("LLM service test passed")

        # Test basic analysis pipeline
        from app.schemas.request import FrontendAnalysisRequest
        from app.services.anlysis_service import APIService

        result = APIService().analyze_frontend_workflow(
            FrontendAnalysisRequest(query="Machine failed during production run", include_details=False, max_results=10)
        )

        if not result.get("success", False):
            logger.error(f"Analysis test failed: {result.get('error_message', 'Unknown error')}")
            return False

        logger.info("Analysis pipeline test passed")
        logger.info("All system tests passed!")
        return True

    except Exception as e:
        logger.error(f"System test failed: {e}", exc_info=True)
        return False


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Ishikawa Knowledge System - AI-powered root cause analysis"
    )
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    subparsers.add_parser("setup", help="Setup and initialize the database")
    subparsers.add_parser("server", help="Start the FastAPI server")
    subparsers.add_parser("test", help="Run system tests")

    args = parser.parse_args()

    # Load and configure
    load_config(args.config) if args.config else load_config()
    config = get_config()
    if args.log_level:
        config.log_level = args.log_level

    setup_logging(level=config.log_level)
    logger.info(f"Ishikawa Knowledge System starting... (Log level: {config.log_level})")

    # Execute command
    if args.command == "setup":
        sys.exit(0 if setup_database(args) else 1)
    elif args.command == "server":
        run_server(args)
    elif args.command == "test":
        sys.exit(0 if test_system(args) else 1)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
