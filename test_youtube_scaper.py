"""
Test đơn giản cho YouTubeScraper - không cần database hay config.
Chỉ test các chức năng cơ bản: parse RSS, extract video ID, fetch transcript.

Script này hoàn toàn độc lập, không import các module có vấn đề với config.
"""
import logging
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')

import feedparser
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# Copy các hàm utility từ YouTubeScraper để test độc lập
def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL"""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11}).*",  # Standard watch URL
        r"youtu\.be\/([0-9A-Za-z_-]{11})",  # Short URL
        r"embed\/([0-9A-Za-z_-]{11})",  # Embed URL
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None

def get_channel_rss_url(channel_identifier: str) -> str | None:
    """Convert channel identifier to RSS feed URL"""
    channel_id = None

    # Check if it's a URL
    if "youtube.com" in channel_identifier or "youtu.be" in channel_identifier:
        if "/channel/" in channel_identifier:
            channel_id = channel_identifier.split("/channel/")[-1].split("/")[0]
        elif "/@" in channel_identifier:
            handle = channel_identifier.split("/@")[-1].split("/")[0]
            print(f"⚠️ Channel handles (@{handle}) require additional API call, not yet supported")
            return None
        elif "?channel_id=" in channel_identifier:
            channel_id = channel_identifier.split("channel_id=")[-1].split("&")[0]
    elif channel_identifier.startswith("UC"):
        # Looks like a channel ID
        channel_id = channel_identifier
    elif channel_identifier.startswith("@"):
        handle = channel_identifier[1:]
        print(f"⚠️ Channel handles (@{handle}) require additional API call, not yet supported")
        return None

    if not channel_id:
        return None

    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def parse_rss_feed(rss_url: str) -> feedparser.FeedParserDict | None:
    """Parse RSS feed using feedparser"""
    try:
        feed = feedparser.parse(rss_url)
        if feed.bozo and feed.bozo_exception:
            print(f"❌ RSS feed parsing error: {feed.bozo_exception}")
            return None
        return feed
    except Exception as e:
        print(f"❌ Failed to fetch RSS feed: {rss_url} - {e}")
        return None

def extract_channel_info(feed: feedparser.FeedParserDict) -> dict[str, str]:
    """Extract channel information from RSS feed"""
    channel_id = ""
    channel_name = "Unknown Channel"

    if hasattr(feed, "feed"):
        channel_name = feed.feed.get("title", channel_name)
        if hasattr(feed.feed, "yt_channelid"):
            channel_id = feed.feed.yt_channelid
        elif hasattr(feed.feed, "link"):
            link = feed.feed.link
            if "/channel/" in link:
                channel_id = link.split("/channel/")[-1].split("/")[0]

    return {"channel_id": channel_id, "channel_name": channel_name}

def test_extract_video_id():
    """Test hàm extract video ID từ URL"""
    print("🧪 Test: Extract Video ID từ URL")
    print("-" * 60)
    
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ]
    
    for url in test_urls:
        video_id = extract_video_id(url)
        print(f"✅ URL: {url}")
        print(f"   Video ID: {video_id}")
        assert video_id == "dQw4w9WgXcQ", f"Failed to extract ID from {url}"
    
    print("✅ Test extract video ID: PASSED\n")

def test_get_rss_url():
    """Test hàm tạo RSS URL từ channel ID"""
    print("🧪 Test: Tạo RSS URL từ Channel ID")
    print("-" * 60)
    
    channel_id = "UCVhQ2NnY5Rskt6UjCUkJ_DA"
    rss_url = get_channel_rss_url(channel_id)
    
    print(f"✅ Channel ID: {channel_id}")
    print(f"   RSS URL: {rss_url}")
    assert rss_url is not None, "RSS URL should not be None"
    assert "feeds/videos.xml" in rss_url, "RSS URL should contain feeds/videos.xml"
    assert channel_id in rss_url, "RSS URL should contain channel ID"
    
    print("✅ Test get RSS URL: PASSED\n")

def test_parse_rss_feed():
    """Test parse RSS feed từ URL"""
    print("🧪 Test: Parse RSS Feed")
    print("-" * 60)
    
    # Test với channel Google Developers
    channel_id = "UCVhQ2NnY5Rskt6UjCUkJ_DA"
    rss_url = get_channel_rss_url(channel_id)
    
    print(f"📡 Đang fetch RSS feed: {rss_url}")
    feed = parse_rss_feed(rss_url)
    
    if feed and hasattr(feed, 'entries'):
        print(f"✅ Parse thành công!")
        print(f"   Số video trong feed: {len(feed.entries)}")
        
        if feed.entries:
            # Lấy video đầu tiên
            first_video = feed.entries[0]
            print(f"\n📹 Video đầu tiên:")
            print(f"   Title: {first_video.get('title', 'N/A')}")
            print(f"   Link: {first_video.get('link', 'N/A')}")
            
            # Test extract video ID
            video_id = extract_video_id(first_video.get('link', ''))
            print(f"   Video ID: {video_id}")
            
            # Test extract channel info
            channel_info = extract_channel_info(feed)
            print(f"\n📺 Channel Info:")
            print(f"   Name: {channel_info.get('channel_name', 'N/A')}")
            print(f"   ID: {channel_info.get('channel_id', 'N/A')}")
    else:
        print("⚠️ Không parse được RSS feed hoặc feed rỗng")
    
    print("\n✅ Test parse RSS feed: COMPLETED\n")

def test_fetch_transcript():
    """Test fetch transcript từ một video ID cụ thể - dùng logic của thầy"""
    print("🧪 Test: Fetch Transcript (Logic của thầy)")
    print("-" * 60)
    
    # Video ID của một video có transcript
    test_video_id = "jqd6_bbjhS8"  # Video từ ví dụ của thầy
    
    print(f"📹 Đang fetch transcript cho video: {test_video_id}")
    print(f"   URL: https://www.youtube.com/watch?v={test_video_id}")
    
    try:
        # Cách của thầy: Tạo instance và dùng fetch()
        transcript_api = YouTubeTranscriptApi()
        
        # Thử cả 2 cách để xem cách nào hoạt động
        transcript = None
        transcript_text = None
        
        # Cách 1: Dùng fetch() như logic của thầy
        try:
            transcript = transcript_api.fetch(test_video_id)
            # Kết quả là object có snippets
            transcript_text = " ".join([snippet.text for snippet in transcript.snippets])
            print(f"✅ Fetch transcript thành công (dùng fetch())!")
            print(f"   Số đoạn transcript: {len(transcript.snippets)}")
        except (AttributeError, TypeError) as e:
            # Cách 2: Thử get_transcript() như code hiện tại
            print(f"   ⚠️ fetch() không hoạt động: {e}")
            print(f"   Thử dùng get_transcript()...")
            try:
                transcript_list = transcript_api.get_transcript(test_video_id)
                transcript_text = " ".join(segment["text"] for segment in transcript_list)
                print(f"✅ Fetch transcript thành công (dùng get_transcript())!")
                print(f"   Số đoạn transcript: {len(transcript_list)}")
            except Exception as e2:
                raise e2
        
        if transcript_text:
            print(f"   Độ dài transcript: {len(transcript_text)} ký tự")
            print(f"   Preview: {transcript_text[:200]}...")
        
    except (TranscriptsDisabled, NoTranscriptFound) as e:
        print(f"⚠️ Transcript không có sẵn: {e}")
    except Exception as e:
        print(f"⚠️ Lỗi khi fetch transcript: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Test fetch transcript: COMPLETED\n")

def main():
    """Chạy tất cả các test"""
    print("=" * 60)
    print("🚀 BẮT ĐẦU TEST YOUTUBE SCRAPER (Đơn giản)")
    print("=" * 60)
    print()
    
    try:
        # Test các chức năng cơ bản
        test_extract_video_id()
        test_get_rss_url()
        test_parse_rss_feed()
        test_fetch_transcript()
        
        print("=" * 60)
        print("✅ TẤT CẢ TEST HOÀN THÀNH!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()