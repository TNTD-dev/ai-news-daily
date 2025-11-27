"""
Streamlit Application for User Profile Management

Giao diện quản lý user profiles với các tính năng:
- Dashboard với thống kê
- Thêm user profile mới
- Xem danh sách users
- Chỉnh sửa và xóa user profiles
"""

import json
import re
from typing import List, Optional

import streamlit as st
from sqlalchemy.orm import Session

from app.database.models import Base, UserProfile
from app.database.repositories import UserProfileRepository
from app.database.session import get_session, init_engine
from app.profiles.user_profile import (
    UserProfileSettings,
    get_default_user_profile,
    save_user_profile,
)

# Page configuration
st.set_page_config(
    page_title="Quản lý User Profiles",
    page_icon="👥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        margin: 1rem 0;
    }
    .user-card {
        background-color: #ffffff;
        padding: 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def init_database_tables():
    """Initialize database tables if they don't exist."""
    try:
        engine = init_engine()
        # Import all models to ensure they're registered in metadata
        # This ensures all tables are created when create_all is called
        from app.database.models import (
            AnthropicArticle,
            Digest,
            OpenAIArticle,
            YouTubeVideo,
        )
        # Create all tables (this is idempotent - won't recreate existing tables)
        Base.metadata.create_all(engine)
    except Exception as e:
        # Only show error if it's not about table already existing
        if "already exists" not in str(e).lower():
            st.error(f"❌ Lỗi khi khởi tạo database: {str(e)}")


def get_db_session():
    """Get database session context manager."""
    return get_session()


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def get_all_users(session: Session) -> List:
    """Get all user profiles from database."""
    repo = UserProfileRepository(session)
    return repo.get_all()


def get_user_by_email(session: Session, email: str):
    """Get user profile by email."""
    repo = UserProfileRepository(session)
    return repo.get_by_email(email)


def delete_user(session: Session, user_id: int) -> bool:
    """Delete user profile by ID."""
    try:
        repo = UserProfileRepository(session)
        success = repo.delete(user_id)
        if success:
            session.commit()
        return success
    except Exception:
        session.rollback()
        return False


# Initialize session state
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "edit_user_email" not in st.session_state:
    st.session_state.edit_user_email = None


def main():
    """Main application function."""
    # Initialize database tables on startup
    init_database_tables()
    
    # Sidebar navigation
    with st.sidebar:
        st.title("👥 User Profile Manager")
        st.markdown("---")
        
        page = st.radio(
            "Điều hướng",
            ["📊 Dashboard", "➕ Thêm User", "📋 Danh sách Users"],
            index=0 if st.session_state.page == "Dashboard" else 
                  1 if st.session_state.page == "Thêm User" else 2,
        )
        
        if page == "📊 Dashboard":
            st.session_state.page = "Dashboard"
        elif page == "➕ Thêm User":
            st.session_state.page = "Thêm User"
        elif page == "📋 Danh sách Users":
            st.session_state.page = "Danh sách Users"
        
        st.markdown("---")
        st.markdown("### ℹ️ Thông tin")
        st.markdown("Quản lý user profiles cho hệ thống AI News Daily")
    
    # Main content area
    if st.session_state.page == "Dashboard":
        show_dashboard()
    elif st.session_state.page == "Thêm User":
        show_add_user()
    elif st.session_state.page == "Danh sách Users":
        show_list_users()


def show_dashboard():
    """Display dashboard with statistics."""
    st.markdown('<h1 class="main-header">📊 Dashboard</h1>', unsafe_allow_html=True)
    
    try:
        session_gen = get_db_session()
        with session_gen as session:
            users = get_all_users(session)
            
            # Calculate statistics
            total_users = len(users)
            subscribers = sum(1 for u in users if u.receive_daily_digest)
            beginner_count = sum(1 for u in users if u.expertise_level == "beginner")
            intermediate_count = sum(1 for u in users if u.expertise_level == "intermediate")
            expert_count = sum(1 for u in users if u.expertise_level == "expert")
            
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("👥 Tổng số Users", total_users)
            
            with col2:
                st.metric("📧 Nhận Daily Digest", subscribers)
            
            with col3:
                st.metric("🌱 Beginner", beginner_count)
            
            with col4:
                st.metric("🎓 Expert", expert_count)
            
            st.markdown("---")
            
            # Expertise level distribution
            if total_users > 0:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📊 Phân bố Expertise Level")
                    expertise_data = {
                        "Beginner": beginner_count,
                        "Intermediate": intermediate_count,
                        "Expert": expert_count,
                    }
                    st.bar_chart(expertise_data)
                
                with col2:
                    st.subheader("📈 Thống kê")
                    st.write(f"**Tổng số users:** {total_users}")
                    st.write(f"**Users nhận digest:** {subscribers} ({subscribers/total_users*100:.1f}%)")
                    st.write(f"**Beginner:** {beginner_count}")
                    st.write(f"**Intermediate:** {intermediate_count}")
                    st.write(f"**Expert:** {expert_count}")
            else:
                st.info("Chưa có user nào trong hệ thống. Hãy thêm user đầu tiên!")
                
    except Exception as e:
        st.error(f"❌ Lỗi khi tải dữ liệu: {str(e)}")


def show_add_user():
    """Display form to add new user."""
    st.markdown('<h1 class="main-header">➕ Thêm User Profile</h1>', unsafe_allow_html=True)
    
    with st.form("add_user_form", clear_on_submit=True):
        st.subheader("Thông tin User")
        
        name = st.text_input("Tên *", placeholder="Nhập tên user")
        email = st.text_input("Email *", placeholder="user@example.com")
        
        st.markdown("---")
        st.subheader("Sở thích")
        
        # Topics options
        topic_options = [
            "ai", "machine learning", "deep learning", "nlp", 
            "computer vision", "robotics", "neural networks",
            "reinforcement learning", "data science", "python"
        ]
        topics = st.multiselect(
            "Chủ đề quan tâm",
            topic_options,
            default=["ai", "machine learning"]
        )
        
        # Providers options
        provider_options = ["openai", "google", "anthropic", "meta", "microsoft"]
        providers = st.multiselect(
            "Nhà cung cấp ưa thích",
            provider_options,
            default=["openai", "google", "anthropic"]
        )
        
        # Formats options
        format_options = ["video", "article", "podcast"]
        formats = st.multiselect(
            "Định dạng nội dung",
            format_options,
            default=["video", "article"]
        )
        
        st.markdown("---")
        st.subheader("Cài đặt")
        
        col1, col2 = st.columns(2)
        
        with col1:
            expertise_level = st.selectbox(
                "Mức độ chuyên môn",
                ["beginner", "intermediate", "expert"],
                index=1
            )
        
        with col2:
            timezone_options = [
                "UTC", "Asia/Ho_Chi_Minh", "America/New_York", 
                "America/Los_Angeles", "Europe/London", "Asia/Tokyo"
            ]
            timezone = st.selectbox("Múi giờ", timezone_options, index=1)
        
        receive_digest = st.checkbox("Nhận daily digest email", value=True)
        
        submitted = st.form_submit_button("➕ Thêm User", type="primary", use_container_width=True)
        
        if submitted:
            # Validation
            if not name or not name.strip():
                st.error("❌ Vui lòng nhập tên!")
                return
            
            if not email or not email.strip():
                st.error("❌ Vui lòng nhập email!")
                return
            
            if not validate_email(email):
                st.error("❌ Email không hợp lệ!")
                return
            
            try:
                session_gen = get_db_session()
                with session_gen as session:
                    # Check if email already exists
                    existing = get_user_by_email(session, email)
                    if existing:
                        st.error(f"❌ Email {email} đã tồn tại trong hệ thống!")
                        return
                    
                    # Create user profile
                    profile = UserProfileSettings(
                        name=name.strip(),
                        email=email.strip(),
                        topics=topics if topics else ["ai", "ml"],
                        providers=providers if providers else ["openai", "google", "anthropic"],
                        formats=formats if formats else ["video", "article"],
                        expertise_level=expertise_level,
                        receive_daily_digest=receive_digest,
                        timezone=timezone,
                    )
                    
                    saved_profile = save_user_profile(session, profile)
                    
                    st.success(f"✅ Đã thêm user thành công! ID: {saved_profile.id}")
                    st.balloons()
                    
            except Exception as e:
                st.error(f"❌ Lỗi khi thêm user: {str(e)}")


def show_list_users():
    """Display list of all users."""
    st.markdown('<h1 class="main-header">📋 Danh sách Users</h1>', unsafe_allow_html=True)
    
    try:
        session_gen = get_db_session()
        with session_gen as session:
            users = get_all_users(session)
            
            if not users:
                st.info("Chưa có user nào trong hệ thống.")
                return
            
            # Search and filter
            col1, col2 = st.columns([3, 1])
            
            with col1:
                search_term = st.text_input("🔍 Tìm kiếm", placeholder="Tìm theo tên hoặc email...")
            
            with col2:
                filter_digest = st.selectbox(
                    "Lọc theo",
                    ["Tất cả", "Nhận digest", "Không nhận digest"]
                )
            
            # Filter users
            filtered_users = users
            if search_term:
                search_lower = search_term.lower()
                filtered_users = [
                    u for u in filtered_users
                    if search_lower in u.name.lower() or search_lower in u.email.lower()
                ]
            
            if filter_digest == "Nhận digest":
                filtered_users = [u for u in filtered_users if u.receive_daily_digest]
            elif filter_digest == "Không nhận digest":
                filtered_users = [u for u in filtered_users if not u.receive_daily_digest]
            
            st.markdown(f"**Tìm thấy {len(filtered_users)} user(s)**")
            st.markdown("---")
            
            # Display users
            for user in filtered_users:
                with st.container():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    
                    with col1:
                        st.markdown(f"### {user.name}")
                        st.markdown(f"📧 {user.email}")
                        
                        # Parse JSON fields
                        try:
                            topics = json.loads(user.preferred_topics)
                            providers = json.loads(user.preferred_providers)
                            formats = json.loads(user.preferred_formats)
                        except:
                            topics = []
                            providers = []
                            formats = []
                        
                        col_info1, col_info2, col_info3 = st.columns(3)
                        with col_info1:
                            st.caption(f"📚 Topics: {', '.join(topics[:3]) if topics else 'N/A'}")
                        with col_info2:
                            st.caption(f"🏢 Providers: {', '.join(providers[:2]) if providers else 'N/A'}")
                        with col_info3:
                            st.caption(f"📊 Level: {user.expertise_level.title()}")
                        
                        digest_status = "✅ Nhận digest" if user.receive_daily_digest else "❌ Không nhận"
                        st.caption(f"{digest_status}")
                    
                    with col2:
                        if st.button("✏️ Sửa", key=f"edit_{user.id}", use_container_width=True):
                            st.session_state.edit_user_email = user.email
                            st.session_state.page = "Chỉnh sửa User"
                            st.rerun()
                    
                    with col3:
                        if st.button("🗑️ Xóa", key=f"delete_{user.id}", use_container_width=True):
                            if delete_user(session, user.id):
                                st.success(f"✅ Đã xóa user {user.name}!")
                                st.rerun()
                            else:
                                st.error("❌ Lỗi khi xóa user!")
                    
                    st.markdown("---")
            
    except Exception as e:
        st.error(f"❌ Lỗi khi tải danh sách users: {str(e)}")
    
    # Handle edit user page
    if st.session_state.get("edit_user_email"):
        st.markdown("---")
        show_edit_user(st.session_state.edit_user_email)


def show_edit_user(email: str):
    """Display form to edit user."""
    st.markdown('<h1 class="main-header">✏️ Chỉnh sửa User</h1>', unsafe_allow_html=True)
    
    try:
        session_gen = get_db_session()
        with session_gen as session:
            user = get_user_by_email(session, email)
            
            if not user:
                st.error("❌ Không tìm thấy user!")
                return
            
            # Parse JSON fields
            try:
                topics = json.loads(user.preferred_topics)
                providers = json.loads(user.preferred_providers)
                formats = json.loads(user.preferred_formats)
            except:
                topics = []
                providers = []
                formats = []
            
            with st.form("edit_user_form"):
                st.subheader("Thông tin User")
                
                name = st.text_input("Tên *", value=user.name)
                email_display = st.text_input("Email *", value=user.email, disabled=True)
                
                st.markdown("---")
                st.subheader("Sở thích")
                
                # Topics options
                topic_options = [
                    "ai", "machine learning", "deep learning", "nlp", 
                    "computer vision", "robotics", "neural networks",
                    "reinforcement learning", "data science", "python"
                ]
                topics_selected = st.multiselect(
                    "Chủ đề quan tâm",
                    topic_options,
                    default=topics
                )
                
                # Providers options
                provider_options = ["openai", "google", "anthropic", "meta", "microsoft"]
                providers_selected = st.multiselect(
                    "Nhà cung cấp ưa thích",
                    provider_options,
                    default=providers
                )
                
                # Formats options
                format_options = ["video", "article", "podcast"]
                formats_selected = st.multiselect(
                    "Định dạng nội dung",
                    format_options,
                    default=formats
                )
                
                st.markdown("---")
                st.subheader("Cài đặt")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    expertise_level = st.selectbox(
                        "Mức độ chuyên môn",
                        ["beginner", "intermediate", "expert"],
                        index=["beginner", "intermediate", "expert"].index(user.expertise_level)
                    )
                
                with col2:
                    timezone_options = [
                        "UTC", "Asia/Ho_Chi_Minh", "America/New_York", 
                        "America/Los_Angeles", "Europe/London", "Asia/Tokyo"
                    ]
                    current_tz_index = timezone_options.index(user.timezone) if user.timezone in timezone_options else 0
                    timezone = st.selectbox("Múi giờ", timezone_options, index=current_tz_index)
                
                receive_digest = st.checkbox("Nhận daily digest email", value=user.receive_daily_digest)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    submitted = st.form_submit_button("💾 Cập nhật", type="primary", use_container_width=True)
                
                with col2:
                    if st.form_submit_button("🗑️ Xóa User", use_container_width=True):
                        if delete_user(session, user.id):
                            st.success("✅ Đã xóa user!")
                            st.session_state.edit_user_email = None
                            st.session_state.page = "Danh sách Users"
                            st.rerun()
                        else:
                            st.error("❌ Lỗi khi xóa user!")
                
                if submitted:
                    # Validation
                    if not name or not name.strip():
                        st.error("❌ Vui lòng nhập tên!")
                        return
                    
                    # Update user profile
                    profile = UserProfileSettings(
                        name=name.strip(),
                        email=user.email,  # Keep original email
                        topics=topics_selected if topics_selected else ["ai", "ml"],
                        providers=providers_selected if providers_selected else ["openai", "google", "anthropic"],
                        formats=formats_selected if formats_selected else ["video", "article"],
                        expertise_level=expertise_level,
                        receive_daily_digest=receive_digest,
                        timezone=timezone,
                    )
                    
                    # Get existing user to update
                    existing_user = get_user_by_email(session, user.email)
                    saved_profile = save_user_profile(session, profile)
                    
                    st.success("✅ Đã cập nhật user thành công!")
                    st.balloons()
                    st.session_state.edit_user_email = None
                    st.session_state.page = "Danh sách Users"
                    st.rerun()
                    
    except Exception as e:
        st.error(f"❌ Lỗi khi chỉnh sửa user: {str(e)}")


if __name__ == "__main__":
    main()

