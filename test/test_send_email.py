"""
Script test gửi email với digest đã tạo.

Script này sẽ:
1. Lấy digest của ngày hôm nay (hoặc ngày chỉ định)
2. Curate content từ digest
3. Gửi email test đến email chỉ định

Usage:
    # Gửi email test với digest hôm nay
    python test_send_email.py test@example.com
    
    # Gửi email test với digest của ngày cụ thể
    python test_send_email.py test@example.com --date 2024-11-27
    
    # Sử dụng user profile từ database
    python test_send_email.py test@example.com --use-profile
    
    # Không cập nhật email_sent status (chỉ test, không đánh dấu đã gửi)
    python test_send_email.py test@example.com --no-mark-sent
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from app.agent.curator import CuratorAgent
from app.agent.email import EmailAgent
from app.config import settings
from app.database.repositories import DigestRepository
from app.database.session import get_session
from app.profiles.user_profile import get_default_user_profile
from app.services.email_service import EmailService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def send_test_email(
    recipient_email: str,
    target_date: date | None = None,
    use_profile: bool = False,
    mark_sent: bool = True,
    preview_html_path: Path | None = None,
) -> bool:
    """
    Gửi email test với digest đã tạo.
    
    Args:
        recipient_email: Email nhận
        target_date: Ngày của digest (mặc định: hôm nay)
        use_profile: Có sử dụng user profile từ database không
        mark_sent: Có đánh dấu digest là đã gửi không
        
    Returns:
        True nếu gửi thành công, False nếu thất bại
    """
    if target_date is None:
        target_date = date.today()
    
    logger.info(f"Bắt đầu test gửi email cho digest ngày {target_date}")
    logger.info(f"Email nhận: {recipient_email}")
    
    # Initialize session
    with get_session() as session:
        # Initialize repositories
        digest_repo = DigestRepository(session)
        
        # Get digest for target date
        digest = digest_repo.get_by_date(target_date)
        if not digest:
            logger.error(f"Không tìm thấy digest cho ngày {target_date}")
            logger.info("Hãy chạy pipeline trước để tạo digest:")
            logger.info("  python -m app.daily_runner")
            return False
        
        logger.info(f"Tìm thấy digest: ID={digest.id}, Title={digest.title}")
        
        # Initialize agents
        curator_agent = CuratorAgent(settings)
        email_agent = EmailAgent(settings)
        email_service = EmailService(settings, session, email_agent)
        
        # Get or create user profile
        if use_profile:
            from app.database.repositories import UserProfileRepository
            from app.profiles.user_profile import UserProfileSettings
            
            user_profile_repo = UserProfileRepository(session)
            user_profile_db = user_profile_repo.get_by_email(recipient_email)
            
            if user_profile_db:
                user_profile = UserProfileSettings.from_db_model(user_profile_db)
                logger.info(f"Sử dụng user profile từ database: {user_profile.name}")
            else:
                logger.warning(f"Không tìm thấy user profile cho {recipient_email}, dùng profile mặc định")
                user_profile = get_default_user_profile(
                    email=recipient_email,
                    name="Test User"
                )
        else:
            # Use default profile
            user_profile = get_default_user_profile(
                email=recipient_email,
                name="Test User"
            )
            logger.info("Sử dụng user profile mặc định")
        
        # Curate content from digest
        logger.info("Đang curate content từ digest...")
        curated_items = curator_agent.curate_from_digest(digest, user_profile)
        logger.info(f"Đã curate {len(curated_items)} items")

        # Build email preview (reused later)
        email_preview = email_agent.compose_digest_email(
            digest=digest,
            curated_items=curated_items,
            prefs=user_profile,
            use_llm_subject=True,
            use_llm_intro=True,
        )

        if preview_html_path:
            try:
                preview_html_path.parent.mkdir(parents=True, exist_ok=True)
                preview_html_path.write_text(email_preview.html_body, encoding="utf-8")
                logger.info(f"Đã lưu HTML preview tại {preview_html_path}")
            except Exception as exc:
                logger.error(f"Không thể lưu HTML preview: {exc}")
        
        # Store original email_sent status for rollback if needed
        original_email_sent = digest.email_sent
        original_email_sent_at = digest.email_sent_at
        
        # Send email
        logger.info("Đang gửi email...")
        success = email_service.send_digest_email(
            digest=digest,
            curated_items=curated_items,
            user_email=recipient_email,
            user_profile=user_profile,
            use_llm_subject=True,
            use_llm_intro=True,
            email_content_override=email_preview,
        )
        
        if success:
            logger.info("✅ Email đã được gửi thành công!")
            
            # Optionally mark as sent (or not, for testing)
            if mark_sent:
                logger.info("Đánh dấu digest là đã gửi")
                # Note: email_service đã tự động đánh dấu nếu gửi thành công
            else:
                logger.info("Không đánh dấu digest là đã gửi (test mode)")
                # Rollback the email_sent status if it was set
                session.refresh(digest)  # Refresh to get latest state
                if digest.email_sent:
                    digest.email_sent = original_email_sent
                    digest.email_sent_at = original_email_sent_at
                    session.commit()
                    logger.info("Đã rollback email_sent status về trạng thái ban đầu")
            
            return True
        else:
            logger.error("❌ Gửi email thất bại")
            return False


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Test gửi email với digest đã tạo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        "email",
        type=str,
        help="Email nhận (ví dụ: test@example.com)",
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Ngày của digest (YYYY-MM-DD), mặc định: hôm nay",
    )
    
    parser.add_argument(
        "--use-profile",
        action="store_true",
        help="Sử dụng user profile từ database thay vì profile mặc định",
    )
    
    parser.add_argument(
        "--no-mark-sent",
        action="store_true",
        help="Không đánh dấu digest là đã gửi (chỉ test)",
    )

    parser.add_argument(
        "--preview-html",
        type=str,
        default=None,
        help="Lưu bản HTML preview đến đường dẫn chỉ định",
    )
    
    args = parser.parse_args()
    
    # Parse date
    target_date = None
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            logger.error(f"Định dạng ngày không hợp lệ: {args.date}. Sử dụng YYYY-MM-DD")
            sys.exit(1)
    
    # Send email
    preview_path = Path(args.preview_html) if args.preview_html else None

    success = send_test_email(
        recipient_email=args.email,
        target_date=target_date,
        use_profile=args.use_profile,
        mark_sent=not args.no_mark_sent,
        preview_html_path=preview_path,
    )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

