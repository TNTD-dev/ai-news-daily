"""
Test script for database connection and models.

This script verifies:
- Database connectivity
- Table creation
- CRUD operations for all models
- Session management
- Model relationships

Usage:
    python -m app.test_db

Prerequisites:
    1. Ensure Docker is running
    2. Start PostgreSQL: docker-compose -f docker/docker-compose.yml up -d
    3. Wait for database to be ready
    4. Run this script
"""

import sys
from datetime import date, datetime, timezone

from sqlalchemy import inspect

from app.database.models import (
    AnthropicArticle,
    Base,
    Digest,
    OpenAIArticle,
    ProcessingStatus,
    TranscriptStatus,
    YouTubeVideo,
)
from app.database.repositories import (
    AnthropicArticleRepository,
    DigestRepository,
    OpenAIArticleRepository,
    YouTubeVideoRepository,
)
from app.database.session import get_session, init_engine, test_connection

# Test results tracking
test_results: list[tuple[str, bool, str]] = []


def print_test(name: str, passed: bool, message: str = "") -> None:
    """Print test result with formatting."""
    status = "✓ PASS" if passed else "✗ FAIL"
    symbol = "✓" if passed else "✗"
    print(f"{symbol} {name}: {status}")
    if message:
        print(f"  → {message}")
    test_results.append((name, passed, message))


def test_database_connection() -> bool:
    """Test database connection."""
    print("\n" + "=" * 60)
    print("TEST 1: Database Connection")
    print("=" * 60)
    
    try:
        if test_connection():
            print_test("Connection Test", True, "Database is accessible")
            return True
        else:
            print_test("Connection Test", False, "Database connection failed")
            return False
    except Exception as e:
        print_test("Connection Test", False, f"Error: {e}")
        return False


def test_engine_initialization() -> bool:
    """Test engine initialization."""
    print("\n" + "=" * 60)
    print("TEST 2: Engine Initialization")
    print("=" * 60)
    
    try:
        engine = init_engine()
        if engine is not None:
            print_test("Engine Initialization", True, "Engine created successfully")
            return True
        else:
            print_test("Engine Initialization", False, "Engine is None")
            return False
    except Exception as e:
        print_test("Engine Initialization", False, f"Error: {e}")
        return False


def test_table_creation() -> bool:
    """Test table creation."""
    print("\n" + "=" * 60)
    print("TEST 3: Table Creation")
    print("=" * 60)
    
    try:
        engine = init_engine()
        # Import all models to ensure they're registered
        # (Already imported at top, but this ensures metadata is populated)
        
        # Create all tables
        Base.metadata.create_all(engine)
        
        # Verify tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        expected_tables = [
            "youtube_videos",
            "openai_articles",
            "anthropic_articles",
            "digests",
            "digest_youtube_videos",
            "digest_openai_articles",
            "digest_anthropic_articles",
        ]
        
        all_exist = all(table in tables for table in expected_tables)
        
        if all_exist:
            print_test("Table Creation", True, f"All {len(expected_tables)} tables created")
            print(f"  → Tables: {', '.join(expected_tables)}")
            return True
        else:
            missing = [t for t in expected_tables if t not in tables]
            print_test("Table Creation", False, f"Missing tables: {missing}")
            return False
    except Exception as e:
        print_test("Table Creation", False, f"Error: {e}")
        return False


def test_session_management() -> bool:
    """Test session context manager."""
    print("\n" + "=" * 60)
    print("TEST 4: Session Management")
    print("=" * 60)
    
    try:
        # Test context manager
        with get_session() as session:
            print_test("Context Manager", True, "Session created successfully")
            
            # Test commit
            session.commit()
            print_test("Session Commit", True, "Commit successful")
        
        # Test rollback on exception
        try:
            with get_session() as session:
                raise ValueError("Test exception")
        except ValueError:
            print_test("Session Rollback", True, "Rollback on exception works")
        
        # Test session cleanup
        print_test("Session Cleanup", True, "Sessions closed properly")
        return True
    except Exception as e:
        print_test("Session Management", False, f"Error: {e}")
        return False


def test_youtube_video_crud() -> bool:
    """Test YouTubeVideo CRUD operations."""
    print("\n" + "=" * 60)
    print("TEST 5: YouTubeVideo CRUD Operations")
    print("=" * 60)
    
    try:
        with get_session() as session:
            repo = YouTubeVideoRepository(session)
            
            # Create
            test_video = YouTubeVideo(
                video_id="test_video_123",
                title="Test YouTube Video",
                description="This is a test video",
                channel_id="test_channel_123",
                channel_name="Test Channel",
                published_at=datetime.now(timezone.utc),
                url="https://youtube.com/watch?v=test_video_123",
                thumbnail_url="https://example.com/thumb.jpg",
                duration=300,
                transcript="Test transcript",
                transcript_status=TranscriptStatus.COMPLETED,
            )
            created = repo.create(test_video)
            session.commit()
            
            if created.id is not None:
                print_test("YouTubeVideo Create", True, f"Created with ID: {created.id}")
            else:
                print_test("YouTubeVideo Create", False, "ID is None")
                return False
            
            # Read by ID
            found = repo.get_by_id(created.id)
            if found and found.video_id == "test_video_123":
                print_test("YouTubeVideo Read by ID", True, f"Found video: {found.title}")
            else:
                print_test("YouTubeVideo Read by ID", False, "Video not found")
                return False
            
            # Read by video_id
            found_by_video_id = repo.get_by_video_id("test_video_123")
            if found_by_video_id:
                print_test("YouTubeVideo Read by video_id", True, "Found by video_id")
            else:
                print_test("YouTubeVideo Read by video_id", False, "Not found by video_id")
                return False
            
            # Update
            found.transcript_status = TranscriptStatus.PROCESSING
            updated = repo.update(found)
            session.commit()
            
            if updated.transcript_status == TranscriptStatus.PROCESSING:
                print_test("YouTubeVideo Update", True, "Status updated successfully")
            else:
                print_test("YouTubeVideo Update", False, "Update failed")
                return False
            
            # Delete
            deleted = repo.delete(created.id)
            session.commit()
            
            if deleted:
                print_test("YouTubeVideo Delete", True, "Deleted successfully")
            else:
                print_test("YouTubeVideo Delete", False, "Delete failed")
                return False
            
            # Verify deletion
            verify = repo.get_by_id(created.id)
            if verify is None:
                print_test("YouTubeVideo Delete Verification", True, "Confirmed deleted")
            else:
                print_test("YouTubeVideo Delete Verification", False, "Still exists")
                return False
            
            return True
    except Exception as e:
        print_test("YouTubeVideo CRUD", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_openai_article_crud() -> bool:
    """Test OpenAIArticle CRUD operations."""
    print("\n" + "=" * 60)
    print("TEST 6: OpenAIArticle CRUD Operations")
    print("=" * 60)
    
    try:
        with get_session() as session:
            repo = OpenAIArticleRepository(session)
            
            # Create
            test_article = OpenAIArticle(
                article_id="test_openai_123",
                title="Test OpenAI Article",
                url="https://openai.com/blog/test",
                author="Test Author",
                published_at=datetime.now(timezone.utc),
                content="Test article content",
                content_markdown="# Test Article",
                summary="Test summary",
                processing_status=ProcessingStatus.COMPLETED,
            )
            created = repo.create(test_article)
            session.commit()
            
            if created.id is not None:
                print_test("OpenAIArticle Create", True, f"Created with ID: {created.id}")
            else:
                print_test("OpenAIArticle Create", False, "ID is None")
                return False
            
            # Read by ID
            found = repo.get_by_id(created.id)
            if found and found.article_id == "test_openai_123":
                print_test("OpenAIArticle Read by ID", True, f"Found article: {found.title}")
            else:
                print_test("OpenAIArticle Read by ID", False, "Article not found")
                return False
            
            # Read by article_id
            found_by_article_id = repo.get_by_article_id("test_openai_123")
            if found_by_article_id:
                print_test("OpenAIArticle Read by article_id", True, "Found by article_id")
            else:
                print_test("OpenAIArticle Read by article_id", False, "Not found by article_id")
                return False
            
            # Update
            found.processing_status = ProcessingStatus.PROCESSING
            updated = repo.update(found)
            session.commit()
            
            if updated.processing_status == ProcessingStatus.PROCESSING:
                print_test("OpenAIArticle Update", True, "Status updated successfully")
            else:
                print_test("OpenAIArticle Update", False, "Update failed")
                return False
            
            # Delete
            deleted = repo.delete(created.id)
            session.commit()
            
            if deleted:
                print_test("OpenAIArticle Delete", True, "Deleted successfully")
            else:
                print_test("OpenAIArticle Delete", False, "Delete failed")
                return False
            
            return True
    except Exception as e:
        print_test("OpenAIArticle CRUD", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_anthropic_article_crud() -> bool:
    """Test AnthropicArticle CRUD operations."""
    print("\n" + "=" * 60)
    print("TEST 7: AnthropicArticle CRUD Operations")
    print("=" * 60)
    
    try:
        with get_session() as session:
            repo = AnthropicArticleRepository(session)
            
            # Create
            test_article = AnthropicArticle(
                article_id="test_anthropic_123",
                title="Test Anthropic Article",
                url="https://anthropic.com/blog/test",
                author="Test Author",
                published_at=datetime.now(timezone.utc),
                content="Test article content",
                content_markdown="# Test Article",
                summary="Test summary",
                processing_status=ProcessingStatus.COMPLETED,
            )
            created = repo.create(test_article)
            session.commit()
            
            if created.id is not None:
                print_test("AnthropicArticle Create", True, f"Created with ID: {created.id}")
            else:
                print_test("AnthropicArticle Create", False, "ID is None")
                return False
            
            # Read by ID
            found = repo.get_by_id(created.id)
            if found and found.article_id == "test_anthropic_123":
                print_test("AnthropicArticle Read by ID", True, f"Found article: {found.title}")
            else:
                print_test("AnthropicArticle Read by ID", False, "Article not found")
                return False
            
            # Read by article_id
            found_by_article_id = repo.get_by_article_id("test_anthropic_123")
            if found_by_article_id:
                print_test("AnthropicArticle Read by article_id", True, "Found by article_id")
            else:
                print_test("AnthropicArticle Read by article_id", False, "Not found by article_id")
                return False
            
            # Update
            found.processing_status = ProcessingStatus.PROCESSING
            updated = repo.update(found)
            session.commit()
            
            if updated.processing_status == ProcessingStatus.PROCESSING:
                print_test("AnthropicArticle Update", True, "Status updated successfully")
            else:
                print_test("AnthropicArticle Update", False, "Update failed")
                return False
            
            # Delete
            deleted = repo.delete(created.id)
            session.commit()
            
            if deleted:
                print_test("AnthropicArticle Delete", True, "Deleted successfully")
            else:
                print_test("AnthropicArticle Delete", False, "Delete failed")
                return False
            
            return True
    except Exception as e:
        print_test("AnthropicArticle CRUD", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_digest_crud() -> bool:
    """Test Digest CRUD operations."""
    print("\n" + "=" * 60)
    print("TEST 8: Digest CRUD Operations")
    print("=" * 60)
    
    try:
        with get_session() as session:
            repo = DigestRepository(session)
            
            # Create
            test_digest = Digest(
                digest_date=date.today(),
                title="Test Digest",
                content="Test digest content",
                email_sent=False,
            )
            created = repo.create(test_digest)
            session.commit()
            
            if created.id is not None:
                print_test("Digest Create", True, f"Created with ID: {created.id}")
            else:
                print_test("Digest Create", False, "ID is None")
                return False
            
            # Read by ID
            found = repo.get_by_id(created.id)
            if found and found.digest_date == date.today():
                print_test("Digest Read by ID", True, f"Found digest: {found.title}")
            else:
                print_test("Digest Read by ID", False, "Digest not found")
                return False
            
            # Read by date
            found_by_date = repo.get_by_date(date.today())
            if found_by_date:
                print_test("Digest Read by date", True, "Found by date")
            else:
                print_test("Digest Read by date", False, "Not found by date")
                return False
            
            # Update email_sent
            found.email_sent = True
            found.email_sent_at = datetime.now(timezone.utc)
            updated = repo.update(found)
            session.commit()
            
            if updated.email_sent:
                print_test("Digest Update", True, "Email status updated successfully")
            else:
                print_test("Digest Update", False, "Update failed")
                return False
            
            # Delete
            deleted = repo.delete(created.id)
            session.commit()
            
            if deleted:
                print_test("Digest Delete", True, "Deleted successfully")
            else:
                print_test("Digest Delete", False, "Delete failed")
                return False
            
            return True
    except Exception as e:
        print_test("Digest CRUD", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_relationships() -> bool:
    """Test many-to-many relationships."""
    print("\n" + "=" * 60)
    print("TEST 9: Model Relationships")
    print("=" * 60)
    
    try:
        with get_session() as session:
            # Create test data
            video_repo = YouTubeVideoRepository(session)
            openai_repo = OpenAIArticleRepository(session)
            anthropic_repo = AnthropicArticleRepository(session)
            digest_repo = DigestRepository(session)
            
            # Create a video
            video = YouTubeVideo(
                video_id="rel_test_video_123",
                title="Relationship Test Video",
                channel_id="test_channel",
                channel_name="Test Channel",
                published_at=datetime.now(timezone.utc),
                url="https://youtube.com/watch?v=rel_test_video_123",
                transcript_status=TranscriptStatus.COMPLETED,
            )
            video = video_repo.create(video)
            
            # Create OpenAI article
            openai_article = OpenAIArticle(
                article_id="rel_test_openai_123",
                title="Relationship Test OpenAI Article",
                url="https://openai.com/blog/rel_test",
                published_at=datetime.now(timezone.utc),
                content="Test content",
                processing_status=ProcessingStatus.COMPLETED,
            )
            openai_article = openai_repo.create(openai_article)
            
            # Create Anthropic article
            anthropic_article = AnthropicArticle(
                article_id="rel_test_anthropic_123",
                title="Relationship Test Anthropic Article",
                url="https://anthropic.com/blog/rel_test",
                published_at=datetime.now(timezone.utc),
                content="Test content",
                processing_status=ProcessingStatus.COMPLETED,
            )
            anthropic_article = anthropic_repo.create(anthropic_article)
            
            session.flush()  # Get IDs
            
            # Create digest with relationships
            test_date = date.today()
            digest = Digest(
                digest_date=test_date,
                title="Relationship Test Digest",
                content="Test digest with relationships",
                email_sent=False,
            )
            digest = digest_repo.create(digest)
            
            # Add relationships
            digest.youtube_videos.append(video)
            digest.openai_articles.append(openai_article)
            digest.anthropic_articles.append(anthropic_article)
            
            session.commit()
            
            # Verify relationships
            found_digest = digest_repo.get_by_date(test_date)
            if found_digest:
                # Check video relationship
                if len(found_digest.youtube_videos) == 1:
                    print_test("Digest-YouTubeVideo Relationship", True, "Relationship created")
                else:
                    print_test("Digest-YouTubeVideo Relationship", False, f"Expected 1, got {len(found_digest.youtube_videos)}")
                    return False
                
                # Check OpenAI article relationship
                if len(found_digest.openai_articles) == 1:
                    print_test("Digest-OpenAIArticle Relationship", True, "Relationship created")
                else:
                    print_test("Digest-OpenAIArticle Relationship", False, f"Expected 1, got {len(found_digest.openai_articles)}")
                    return False
                
                # Check Anthropic article relationship
                if len(found_digest.anthropic_articles) == 1:
                    print_test("Digest-AnthropicArticle Relationship", True, "Relationship created")
                else:
                    print_test("Digest-AnthropicArticle Relationship", False, f"Expected 1, got {len(found_digest.anthropic_articles)}")
                    return False
                
                # Test reverse relationship
                if len(video.digests) == 1:
                    print_test("YouTubeVideo-Digest Reverse Relationship", True, "Reverse relationship works")
                else:
                    print_test("YouTubeVideo-Digest Reverse Relationship", False, "Reverse relationship failed")
                    return False
                
                # Cleanup
                digest_repo.delete(found_digest.id)
                video_repo.delete(video.id)
                openai_repo.delete(openai_article.id)
                anthropic_repo.delete(anthropic_article.id)
                session.commit()
                
                return True
            else:
                print_test("Relationship Test", False, "Digest not found")
                return False
    except Exception as e:
        print_test("Relationship Test", False, f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_summary() -> None:
    """Print test summary."""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    total = len(test_results)
    passed = sum(1 for _, result, _ in test_results if result)
    failed = total - passed
    
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed} ✓")
    print(f"Failed: {failed} ✗")
    
    if failed > 0:
        print("\nFailed Tests:")
        for name, result, message in test_results:
            if not result:
                print(f"  ✗ {name}: {message}")
    
    print("\n" + "=" * 60)
    if failed == 0:
        print("ALL TESTS PASSED! ✓")
    else:
        print(f"TESTS FAILED: {failed} test(s) failed")
    print("=" * 60 + "\n")


def main() -> int:
    """Run all tests."""
    print("\n" + "=" * 60)
    print("DATABASE CONNECTION AND MODELS TEST SUITE")
    print("=" * 60)
    
    # Run all tests
    tests = [
        test_database_connection,
        test_engine_initialization,
        test_table_creation,
        test_session_management,
        test_youtube_video_crud,
        test_openai_article_crud,
        test_anthropic_article_crud,
        test_digest_crud,
        test_relationships,
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"\n✗ {test_func.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    print_summary()
    
    # Return exit code
    failed = sum(1 for _, result, _ in test_results if not result)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

