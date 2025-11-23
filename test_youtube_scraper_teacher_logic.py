"""
Test script theo đúng logic của thầy để so sánh với code hiện tại.
"""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import os
import feedparser
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from youtube_transcript_api.proxies import WebshareProxyConfig

class Transcript(BaseModel):
    text: str

class ChannelVideo(BaseModel):
    title: str
    url: str
    video_id: str
    published_at: datetime
    description: str
    transcript: Optional[str] = None

class YouTubeScraper:
    def __init__(self):
        proxy_config = None
        proxy_username = os.getenv("PROXY_USERNAME")
        proxy_password = os.getenv("PROXY_PASSWORD")
        
        if proxy_username and proxy_password:
            proxy_config = WebshareProxyConfig(
                proxy_username=proxy_username,
                proxy_password=proxy_password
            )
        
        self.transcript_api = YouTubeTranscriptApi(proxy_config=proxy_config)

    def _get_rss_url(self, channel_id: str) -> str:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    def _extract_video_id(self, video_url: str) -> str:
        if "youtube.com/watch?v=" in video_url:
            return video_url.split("v=")[1].split("&")[0]
        if "youtube.com/shorts/" in video_url:
            return video_url.split("shorts/")[1].split("?")[0]
        if "youtu.be/" in video_url:
            return video_url.split("youtu.be/")[1].split("?")[0]
        return video_url

    def get_transcript(self, video_id: str) -> Optional[Transcript]:
        try:
            transcript = self.transcript_api.fetch(video_id)
            text = " ".join([snippet.text for snippet in transcript.snippets])
            return Transcript(text=text)
        except (TranscriptsDisabled, NoTranscriptFound):
            return None
        except Exception as e:
            print(f"⚠️ Lỗi khi fetch transcript: {e}")
            return None

    def get_latest_videos(self, channel_id: str, hours: int = 24) -> list[ChannelVideo]:
        feed = feedparser.parse(self._get_rss_url(channel_id))
        if not feed.entries:
            return []
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        videos = []
        
        for entry in feed.entries:
            if "/shorts/" in entry.link:
                continue
            published_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if published_time >= cutoff_time:
                video_id = self._extract_video_id(entry.link)
                videos.append(ChannelVideo(
                    title=entry.title,
                    url=entry.link,
                    video_id=video_id,
                    published_at=published_time,
                    description=entry.get("summary", "")
                ))
        
        return videos

    def scrape_channel(self, channel_id: str, hours: int = 150) -> list[ChannelVideo]:
        videos = self.get_latest_videos(channel_id, hours)
        result = []
        for video in videos:
            transcript = self.get_transcript(video.video_id)
            result.append(video.model_copy(update={"transcript": transcript.text if transcript else None}))
        return result

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 TEST THEO LOGIC CỦA THẦY")
    print("=" * 60)
    print()
    
    scraper = YouTubeScraper()
    
    # Test 1: Fetch transcript cho 1 video
    print("📹 Test 1: Fetch transcript cho video jqd6_bbjhS8")
    print("-" * 60)
    transcript: Transcript = scraper.get_transcript("jqd6_bbjhS8")
    if transcript:
        print(f"✅ Thành công! Độ dài: {len(transcript.text)} ký tự")
        print(f"Preview: {transcript.text[:200]}...")
    else:
        print("❌ Không lấy được transcript")
    print()
    
    # Test 2: Scrape channel
    print("📺 Test 2: Scrape channel UCVhQ2NnY5Rskt6UjCUkJ_DA (Google Developers)")
    print("-" * 60)
    channel_videos: List[ChannelVideo] = scraper.scrape_channel("UCVhQ2NnY5Rskt6UjCUkJ_DA", hours=200)
    print(f"✅ Tìm thấy {len(channel_videos)} video")
    
    for i, video in enumerate(channel_videos[:3], 1):  # Chỉ hiển thị 3 video đầu
        print(f"\n{i}. {video.title}")
        print(f"   Video ID: {video.video_id}")
        print(f"   Published: {video.published_at}")
        if video.transcript:
            print(f"   Transcript: ✅ ({len(video.transcript)} ký tự)")
        else:
            print(f"   Transcript: ❌")
    
    print("\n" + "=" * 60)
    print("✅ TEST HOÀN THÀNH")
    print("=" * 60)

