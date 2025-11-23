"""
Database session management for the AI News Aggregator application.

This module provides centralized database session management for PostgreSQL using
SQLAlchemy 2.0+. It handles engine creation, session factory setup, and provides
a context manager for safe session usage with proper cleanup.

Key Features:
    - Engine initialization with configurable connection pooling
    - Session factory for creating database sessions
    - Context manager for automatic session cleanup
    - Connection testing function to verify database accessibility
    - Error handling for connection failures
    - Thread-safe session management

Usage:
    ```python
    from app.database.session import get_session
    
    # Using context manager (recommended)
    with get_session() as session:
        # Use session for database operations
        repo = YouTubeVideoRepository(session)
        videos = repo.get_all()
        session.commit()
    
    # Using dependency injection pattern
    from app.database.session import get_db
    
    for session in get_db():
        # Use session
        pass
    
    # Testing database connection
    from app.database.session import test_connection
    
    if test_connection():
        print("Database is accessible!")
    ```
"""

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import DatabaseConfig, settings

logger = logging.getLogger(__name__)

# Global engine instance (initialized on first use)
_engine: Engine | None = None

# Session factory (initialized after engine creation)
SessionLocal: sessionmaker[Session] | None = None


def init_engine(config: DatabaseConfig | None = None) -> Engine:
    """
    Initialize SQLAlchemy database engine with connection pooling.
    
    Creates a database engine from the provided configuration or uses
    the global settings. Configures connection pooling for efficient
    connection management.
    
    Args:
        config: Optional DatabaseConfig instance. If None, uses settings.database
        
    Returns:
        Initialized SQLAlchemy Engine instance
        
    Raises:
        SQLAlchemyError: If engine creation fails (e.g., invalid connection string)
        ValueError: If database URL is missing or invalid
        
    Connection Pool Configuration:
        - pool_size=5: Number of connections to maintain in the pool
        - max_overflow=10: Additional connections beyond pool_size
        - pool_pre_ping=True: Verify connections before using (handles stale connections)
        - pool_recycle=3600: Recycle connections after 1 hour (prevents timeout issues)
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    # Use provided config or fall back to global settings
    db_config = config or settings.database
    
    if not db_config.url:
        raise ValueError("Database URL is required. Set DATABASE_URL environment variable.")
    
    try:
        _engine = create_engine(
            db_config.url,
            echo=db_config.echo,
            pool_size=db_config.pool_size,
            max_overflow=db_config.max_overflow,
            pool_pre_ping=True,  # Always enabled for connection health checks
            pool_recycle=db_config.pool_recycle,
            pool_timeout=db_config.pool_timeout,
        )
        
        logger.info(
            f"Database engine initialized successfully "
            f"(pool_size={db_config.pool_size}, max_overflow={db_config.max_overflow})"
        )
        return _engine
        
    except SQLAlchemyError as e:
        logger.error(f"Failed to create database engine: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating database engine: {e}")
        raise SQLAlchemyError(f"Failed to initialize database engine: {e}") from e


def get_session_factory() -> sessionmaker[Session]:
    """
    Get or create the session factory.
    
    Initializes the engine if not already initialized, then creates
    and returns the session factory bound to the engine.
    
    Returns:
        Session factory (sessionmaker) for creating database sessions
        
    Raises:
        SQLAlchemyError: If engine initialization fails
    """
    global SessionLocal
    
    if SessionLocal is not None:
        return SessionLocal
    
    # Ensure engine is initialized
    engine = init_engine()
    
    # Create session factory with explicit transaction control
    SessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,  # Explicit commit control
        autoflush=False,   # Explicit flush control
        expire_on_commit=True,  # Expire objects after commit
    )
    
    logger.debug("Session factory created")
    return SessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic cleanup.
    
    Provides a database session that is automatically committed on success,
    rolled back on exception, and closed in all cases. This ensures proper
    resource cleanup and transaction management.
    
    Yields:
        SQLAlchemy Session instance
        
    Raises:
        SQLAlchemyError: If session creation or operations fail
        
    Example:
        ```python
        with get_session() as session:
            repo = YouTubeVideoRepository(session)
            video = repo.get_by_id(1)
            session.commit()
        ```
    """
    session_factory = get_session_factory()
    session: Session = session_factory()
    
    try:
        yield session
        session.commit()
        logger.debug("Session committed successfully")
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Database error occurred, rolling back transaction: {e}")
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Unexpected error in session, rolling back transaction: {e}")
        raise
    finally:
        session.close()
        logger.debug("Session closed")


def get_db() -> Generator[Session, None, None]:
    """
    Dependency-style function that yields a database session.
    
    This is useful for dependency injection patterns (e.g., FastAPI).
    The session is automatically closed after use. The caller is responsible
    for committing or rolling back transactions.
    
    Yields:
        SQLAlchemy Session instance
        
    Raises:
        SQLAlchemyError: If session creation fails
        
    Example:
        ```python
        for session in get_db():
            repo = YouTubeVideoRepository(session)
            videos = repo.get_all()
            session.commit()
        ```
    """
    session_factory = get_session_factory()
    session: Session = session_factory()
    
    try:
        yield session
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_db: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def test_connection(config: DatabaseConfig | None = None) -> bool:
    """
    Test database connection to verify accessibility.
    
    Attempts to establish a connection to the database and execute
    a simple query to verify the database is accessible and responsive.
    
    Args:
        config: Optional DatabaseConfig instance. If None, uses settings.database
        
    Returns:
        True if connection test succeeds, False otherwise
        
    Example:
        ```python
        from app.database.session import test_connection
        
        if test_connection():
            print("Database connection successful!")
        else:
            print("Database connection failed!")
        ```
    """
    db_config = config or settings.database
    
    if not db_config.url:
        logger.error("Cannot test connection: Database URL is not configured")
        return False
    
    try:
        # Create a temporary engine for testing (don't use global engine)
        test_engine = create_engine(
            db_config.url,
            echo=False,
            pool_pre_ping=True,
            # Use minimal pool settings for test
            pool_size=1,
            max_overflow=0,
        )
        
        # Test connection with a simple query
        with test_engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        
        # Dispose of test engine
        test_engine.dispose()
        
        logger.info("Database connection test successful")
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"Database connection test failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during connection test: {e}")
        return False


def close_engine() -> None:
    """
    Close the database engine and cleanup resources.
    
    This should be called during application shutdown to properly
    close all database connections and free resources.
    
    Note:
        This is typically called automatically when the application exits,
        but can be called explicitly for graceful shutdown.
    """
    global _engine, SessionLocal
    
    if _engine is not None:
        _engine.dispose()
        _engine = None
        logger.info("Database engine closed")
    
    SessionLocal = None

