"""
Ishikawa Knowledge System
=========================

A graph-based, LLM-enhanced root cause analysis system using the Ishikawa (Fishbone)
diagram methodology for industrial engineering applications.

This system combines:
- Neo4j graph database for knowledge storage
- LangGraph for orchestrating multi-step reasoning
- Ollama for local LLM inference
- FastAPI for REST API endpoints

Key Features:
- Intent extraction from natural language queries
- Multi-strategy knowledge base search
- Structured Ishikawa diagram generation
- 5 Whys analysis reconstruction
- Domain-aware root cause analysis
"""

__version__ = "1.0.0"
__author__ = "Ishikawa Knowledge System Team"