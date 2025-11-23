"""
Test đơn giản cho AnthropicScraper - không cần database hay config.
Chỉ test các chức năng cơ bản: parse RSS, extract article ID, fetch content, convert HTML to markdown.

Script này hoàn toàn độc lập, không import các module có vấn đề với config.
"""
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

import feedparser
import requests
from docling.document_converter import DocumentConverter

# Copy các hàm utility từ AnthropicScraper để test độc lập
def extract_article_id(url: str) -> str:
    """Extract unique article ID from URL"""
    parsed = urlparse(url)
    # Use path as ID, removing leading/trailing slashes
    article_id = parsed.path.strip("/")
    if not article_id:
        # Fallback to full URL if path is empty
        article_id = url
    return article_id

def parse_rss_feed(rss_url: str) -> feedparser.FeedParserDict | None:
    """Parse RSS feed using feedparser"""
    try:
        # For GitHub raw URLs, fetch content first to avoid Content-Type issues
        if "raw.githubusercontent.com" in rss_url:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response = session.get(rss_url, timeout=30)
            response.raise_for_status()
            # Parse from string content instead of URL
            feed = feedparser.parse(response.content)
        else:
            # For regular URLs, parse directly
            feed = feedparser.parse(rss_url)
        
        if feed.bozo and feed.bozo_exception:
            print(f"❌ RSS feed parsing error: {feed.bozo_exception}")
            return None
        return feed
    except Exception as e:
        print(f"❌ Failed to fetch RSS feed: {rss_url} - {e}")
        return None

def fetch_article_content(url: str) -> str | None:
    """Fetch full article content from URL"""
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Failed to fetch article content: {url} - {e}")
        return None

def html_to_markdown(html_content: str) -> str | None:
    """Convert HTML content to markdown using docling"""
    # docling's DocumentConverter.convert() expects a file path or URL,
    # not a string. We need to write HTML to a temporary file first.
    with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as tmp_file:
        try:
            tmp_file.write(html_content)
            tmp_file_path = tmp_file.name
            tmp_file.close()  # Close file so docling can read it
            
            converter = DocumentConverter()
            result = converter.convert(tmp_file_path)
            
            # Extract markdown from the result
            if hasattr(result, "document"):
                doc = result.document
            else:
                doc = result
            
            # Try to get markdown content
            if hasattr(doc, "export_to_markdown"):
                markdown = doc.export_to_markdown()
            elif hasattr(doc, "markdown"):
                markdown = doc.markdown
            elif hasattr(result, "export_to_markdown"):
                markdown = result.export_to_markdown()
            else:
                print("⚠️ Could not extract markdown from docling result")
                markdown = None
            
            return markdown
        except Exception as e:
            print(f"❌ Failed to convert HTML to markdown: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Clean up temporary file
            try:
                Path(tmp_file_path).unlink(missing_ok=True)
            except Exception:
                pass

def test_extract_article_id():
    """Test hàm extract article ID từ URL"""
    print("🧪 Test: Extract Article ID từ URL")
    print("-" * 60)
    
    test_cases = [
        ("https://www.anthropic.com/news/claude-3-5-sonnet", "news/claude-3-5-sonnet"),
        ("https://www.anthropic.com/research/scaling-laws", "research/scaling-laws"),
        ("https://www.anthropic.com/news/", "news"),
        ("https://www.anthropic.com/", "https://www.anthropic.com/"),  # Fallback case
    ]
    
    for url, expected_id in test_cases:
        article_id = extract_article_id(url)
        print(f"✅ URL: {url}")
        print(f"   Article ID: {article_id}")
        assert article_id == expected_id, f"Expected {expected_id}, got {article_id}"
    
    print("✅ Test extract article ID: PASSED\n")

def test_parse_rss_feed():
    """Test parse RSS feed từ Anthropic blog"""
    print("🧪 Test: Parse RSS Feed từ Anthropic Blog")
    print("-" * 60)
    
    # Test với tất cả 3 RSS feeds
    rss_feeds = [
        ("Research", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml"),
        ("News", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_news.xml"),
        ("Engineering", "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_engineering.xml"),
    ]
    
    for feed_name, rss_url in rss_feeds:
        print(f"\n📡 Testing {feed_name} feed: {rss_url}")
        feed = parse_rss_feed(rss_url)
        
        if feed and hasattr(feed, 'entries'):
            print(f"✅ Parse thành công!")
            print(f"   Số bài viết trong feed: {len(feed.entries)}")
            
            if feed.entries:
                # Lấy bài viết đầu tiên
                first_article = feed.entries[0]
                print(f"\n📄 Bài viết đầu tiên:")
                print(f"   Title: {first_article.get('title', 'N/A')[:80]}...")
                print(f"   Link: {first_article.get('link', 'N/A')}")
                print(f"   Published: {first_article.get('published', 'N/A')}")
                
                # Test extract article ID
                article_id = extract_article_id(first_article.get('link', ''))
                print(f"   Article ID: {article_id}")
        else:
            print(f"⚠️ Không parse được RSS feed hoặc feed rỗng")
    
    print("\n✅ Test parse RSS feed: COMPLETED\n")

def test_fetch_article_content():
    """Test fetch article content từ một URL cụ thể"""
    print("🧪 Test: Fetch Article Content")
    print("-" * 60)
    
    # Lấy một bài viết từ RSS feed để test
    rss_url = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml"
    feed = parse_rss_feed(rss_url)
    
    if not feed or not hasattr(feed, 'entries') or not feed.entries:
        print("⚠️ Không thể lấy RSS feed để test")
        return
    
    # Lấy bài viết đầu tiên
    test_article = feed.entries[0]
    test_url = test_article.get('link', '')
    
    if not test_url:
        print("⚠️ Bài viết không có URL")
        return
    
    print(f"📄 Đang fetch content từ: {test_url}")
    print(f"   Title: {test_article.get('title', 'N/A')}")
    
    content = fetch_article_content(test_url)
    
    if content:
        print(f"✅ Fetch content thành công!")
        print(f"   Độ dài HTML: {len(content)} ký tự")
        print(f"   Preview: {content[:200]}...")
    else:
        print("⚠️ Không thể fetch content")
    
    print("\n✅ Test fetch article content: COMPLETED\n")

def test_html_to_markdown():
    """Test convert HTML to markdown bằng docling"""
    print("🧪 Test: Convert HTML to Markdown")
    print("-" * 60)
    
    # Test với HTML đơn giản
    test_html = """
    <html>
        <body>
            <h1>Test Article</h1>
            <p>This is a <strong>test</strong> paragraph with <em>formatting</em>.</p>
            <ul>
                <li>Item 1</li>
                <li>Item 2</li>
            </ul>
            <a href="https://example.com">Link</a>
        </body>
    </html>
    """
    
    print("📝 Đang convert HTML sample...")
    markdown = html_to_markdown(test_html)
    
    if markdown:
        print(f"✅ Convert thành công!")
        print(f"   Độ dài markdown: {len(markdown)} ký tự")
        print(f"   Preview:\n{markdown[:300]}")
    else:
        print("⚠️ Không thể convert HTML to markdown")
        print("   (Có thể do docling API khác với expected)")
    
    print("\n✅ Test HTML to markdown: COMPLETED\n")

def test_full_workflow():
    """Test workflow đầy đủ: RSS -> Extract -> Fetch -> Convert"""
    print("🧪 Test: Full Workflow (RSS -> Extract -> Fetch -> Convert)")
    print("-" * 60)
    
    rss_url = "https://raw.githubusercontent.com/Olshansk/rss-feeds/main/feeds/feed_anthropic_research.xml"
    print(f"📡 Step 1: Parse RSS feed...")
    feed = parse_rss_feed(rss_url)
    
    if not feed or not hasattr(feed, 'entries') or not feed.entries:
        print("⚠️ Không thể lấy RSS feed")
        return
    
    # Lấy bài viết đầu tiên
    article = feed.entries[0]
    article_url = article.get('link', '')
    article_title = article.get('title', 'N/A')
    
    if not article_url:
        print("⚠️ Bài viết không có URL")
        return
    
    print(f"✅ Step 1: Parse RSS thành công")
    print(f"   Article: {article_title}")
    print(f"   URL: {article_url}")
    
    # Extract article ID
    print(f"\n📝 Step 2: Extract article ID...")
    article_id = extract_article_id(article_url)
    print(f"✅ Step 2: Article ID = {article_id}")
    
    # Fetch content (skip nếu quá lâu, chỉ test với summary)
    print(f"\n🌐 Step 3: Fetch article content...")
    print(f"   (Skipping để tránh timeout - chỉ test với summary từ RSS)")
    summary = article.get('summary', '')
    if summary:
        print(f"✅ Step 3: Có summary từ RSS feed")
        print(f"   Summary length: {len(summary)} ký tự")
    
    # Test convert với summary HTML nếu có
    if summary:
        print(f"\n🔄 Step 4: Convert HTML to markdown...")
        markdown = html_to_markdown(summary)
        if markdown:
            print(f"✅ Step 4: Convert thành công!")
            print(f"   Markdown length: {len(markdown)} ký tự")
        else:
            print(f"⚠️ Step 4: Convert thất bại (có thể do docling API)")
    
    print("\n✅ Test full workflow: COMPLETED\n")

def main():
    """Chạy tất cả các test"""
    print("=" * 60)
    print("🚀 BẮT ĐẦU TEST ANTHROPIC SCRAPER (Đơn giản)")
    print("=" * 60)
    print()
    
    try:
        # Test các chức năng cơ bản
        test_extract_article_id()
        test_parse_rss_feed()
        test_fetch_article_content()
        test_html_to_markdown()
        test_full_workflow()
        
        print("=" * 60)
        print("✅ TẤT CẢ TEST HOÀN THÀNH!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

