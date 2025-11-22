"""
Test script đơn giản để kiểm tra việc lấy transcript từ YouTube.

Script này độc lập, không cần database hay config.
Chạy trực tiếp: python test_youtube_transcript.py
"""
import sys
import youtube_transcript_api

print("="*60)
print(f"Python đang lấy thư viện từ đường dẫn này:")
print(youtube_transcript_api.__file__)
print("="*60)


from youtube_transcript_api import (
    TranscriptsDisabled,
    NoTranscriptFound,
    YouTubeTranscriptApi,
)


def test_transcript(video_id: str = "dQw4w9WgXcQ"):
    """
    Test function để kiểm tra việc lấy transcript từ YouTube video.
    
    Args:
        video_id: YouTube video ID để test (mặc định: dQw4w9WgXcQ)
    
    Usage:
        python test_youtube_transcript.py
        Hoặc trong Interactive Window: test_transcript("YOUR_VIDEO_ID")
    """
    print(f"Testing transcript fetching for video: {video_id}")
    print("=" * 60)
    
    try:
        # Fetch transcript
        print("Fetching transcript...")
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        
        # Combine transcript segments
        transcript_text = " ".join(segment["text"] for segment in transcript_list)
        
        print("✓ Successfully fetched transcript!")
        print(f"\nTranscript length: {len(transcript_text)} characters")
        print(f"Number of segments: {len(transcript_list)}")
        print(f"\nFirst 200 characters:")
        print("-" * 60)
        print(transcript_text[:200] + "...")
        print("-" * 60)
        
        return True
        
    except TranscriptsDisabled:
        print("✗ Transcripts are disabled for this video")
        print("   Try a different video ID")
        return False
        
    except NoTranscriptFound:
        print("✗ No transcript found for this video")
        print("   This video may not have transcripts available")
        return False
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":

    
    # Uncomment để test với video khác:
    test_transcript("E8zpgNPx8jE")

