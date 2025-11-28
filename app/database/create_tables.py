"""
Script to create all database tables.

Chạy script này một lần để tạo tất cả các bảng trong database,
bao gồm cả bảng user_profiles.

Usage:
    python -m app.database.create_tables
"""

from app.database.models import (
    AnthropicArticle,
    Base,
    Digest,
    OpenAIArticle,
    UserProfile,
    YouTubeVideo,
)
from app.database.session import init_engine

if __name__ == "__main__":
    print("Đang khởi tạo database engine...")
    engine = init_engine()
    
    print("Đang tạo tất cả các bảng...")
    Base.metadata.create_all(engine)
    
    print("✅ Đã tạo tất cả các bảng thành công!")
    print("\nCác bảng đã được tạo:")
    print("  - youtube_videos")
    print("  - openai_articles")
    print("  - anthropic_articles")
    print("  - digests")
    print("  - user_profiles")
    print("  - digest_youtube_videos (association table)")
    print("  - digest_openai_articles (association table)")
    print("  - digest_anthropic_articles (association table)")

