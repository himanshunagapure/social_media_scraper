import json
import time
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import requests
from instagrapi import Client
from instagrapi.exceptions import (
    LoginRequired, 
    ChallengeRequired, 
    UserNotFound,
    MediaNotFound,
    RateLimitError,
    ClientError
)
from dotenv import load_dotenv
import os

class InstagramScraper:
    def __init__(self, username: str, password: str, session_file: str = "session.json", 
                 proxy: Optional[str] = None, delay_range: tuple = (5, 10)):
        """
        Initialize Instagram scraper with security and efficiency features
        
        Args:
            username: Instagram username
            password: Instagram password
            session_file: File to store session data
            proxy: Proxy URL (optional)
            delay_range: Tuple of min and max delay between requests
        """
        self.username = username
        self.password = password
        self.session_file = session_file
        self.proxy = proxy
        self.delay_range = delay_range
        self.client = Client()
        self.logged_in = False
        
        # Setup logging
        self.setup_logging()
        
        # User agents for rotation
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0"
        ]
        
        # Configure client settings
        self.setup_client()
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('instagram_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_client(self):
        """Configure client with security settings"""
        # Rotate user agent
        user_agent = random.choice(self.user_agents)
        self.client.set_user_agent(user_agent)
        
        # Set proxy if provided
        if self.proxy:
            self.client.set_proxy(self.proxy)
        
        # Configure delays
        self.client.delay_range = self.delay_range
    
    def random_delay(self):
        """Add random delay between requests"""
        delay = random.uniform(*self.delay_range)
        self.logger.info(f"Waiting {delay:.2f} seconds...")
        time.sleep(delay)
    
    def save_session(self):
        """Save session data to file"""
        try:
            session_data = self.client.get_settings()
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            self.logger.info("Session saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving session: {e}")
    
    def clear_session(self):
        """Clear session data and delete session file"""
        try:
            if Path(self.session_file).exists():
                Path(self.session_file).unlink()
                self.logger.info("Session file deleted")
            self.client.set_settings({})
            self.logged_in = False
        except Exception as e:
            self.logger.error(f"Error clearing session: {e}")
    
    def load_session(self) -> bool:
        """Load session data from file with better error handling"""
        try:
            if Path(self.session_file).exists():
                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)
                
                # Validate session data
                if not session_data or 'cookies' not in session_data:
                    self.logger.warning("Invalid session data, clearing...")
                    self.clear_session()
                    return False
                
                self.client.set_settings(session_data)
                
                # Test if session is still valid
                try:
                    self.client.login(self.username, self.password)
                    self.logged_in = True
                    self.logger.info("Session loaded successfully")
                    return True
                except Exception as e:
                    self.logger.warning(f"Session expired: {e}")
                    self.clear_session()
                    return False
        except Exception as e:
            self.logger.error(f"Error loading session: {e}")
            self.clear_session()
        return False
    
    def login(self) -> bool:
        """Login to Instagram with error handling and CSRF token fixes"""
        try:
            # Clear any existing session data first
            self.client.set_settings({})
            
            # Try to load existing session first
            if self.load_session():
                return True
            
            # Fresh login with CSRF token handling
            self.logger.info("Attempting fresh login...")
            
            # Set device settings to avoid CSRF issues
            self.client.set_device({
                "app_version": "269.0.0.18.75",
                "android_version": 26,
                "android_release": "8.0.0",
                "dpi": "480dpi",
                "resolution": "1080x1920",
                "manufacturer": "OnePlus",
                "device": "OnePlus 6T",
                "model": "ONEPLUS A6013",
                "cpu": "qcom",
                "version_code": "314665256"
            })
            
            # Set user agent to a more recent one
            self.client.set_user_agent(
                "Instagram 269.0.0.18.75 Android (26/8.0.0; 480dpi; 1080x1920; OnePlus; OnePlus 6T; ONEPLUS A6013; qcom; en_US; 314665256)"
            )
            
            # Login with retry mechanism
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.client.login(self.username, self.password)
                    self.logged_in = True
                    self.save_session()
                    self.logger.info("Login successful")
                    return True
                except Exception as e:
                    self.logger.warning(f"Login attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(5)  # Wait before retry
                        continue
                    else:
                        raise e
                        
        except ChallengeRequired as e:
            self.logger.error(f"Challenge required: {e}")
            return False
        except LoginRequired as e:
            self.logger.error(f"Login required: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return False
    
    def handle_rate_limit(self, func, *args, **kwargs):
        """Handle rate limiting with exponential backoff"""
        max_retries = 3
        base_delay = 30
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except RateLimitError as e:
                if attempt == max_retries - 1:
                    raise e
                
                delay = base_delay * (2 ** attempt) + random.uniform(0, 10)
                self.logger.warning(f"Rate limit hit, waiting {delay:.2f} seconds...")
                time.sleep(delay)
            except Exception as e:
                self.logger.error(f"Error in {func.__name__}: {e}")
                raise e
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Get user information"""
        try:
            if not self.logged_in:
                self.logger.error("Not logged in")
                return None
            
            self.random_delay()
            user_info = self.handle_rate_limit(self.client.user_info_by_username, username)
            
            return {
                'user_id': user_info.pk,
                'username': user_info.username,
                'full_name': user_info.full_name,
                'biography': user_info.biography,
                'followers_count': user_info.follower_count,
                'following_count': user_info.following_count,
                'media_count': user_info.media_count,
                'is_private': user_info.is_private,
                'is_verified': user_info.is_verified,
                'profile_pic_url': user_info.profile_pic_url,
                'external_url': user_info.external_url,
                'scraped_at': datetime.now().isoformat()
            }
        except UserNotFound:
            self.logger.error(f"User {username} not found")
            return None
        except Exception as e:
            self.logger.error(f"Error getting user info: {e}")
            return None
    
    def get_user_media(self, username: str, count: int = 20) -> List[Dict]:
        """Get user's media posts using the v1 endpoint"""
        from pydantic import ValidationError
        try:
            if not self.logged_in:
                self.logger.error("Not logged in")
                return []
            
            self.random_delay()
            user_id = self.client.user_id_from_username(username)
            
            self.random_delay()
            try:
                # Use the v1 endpoint directly
                media_items = self.handle_rate_limit(self.client.user_medias_v1, user_id, count)
            except ValidationError as ve:
                self.logger.warning(f"Validation error in user_medias_v1 call: {ve}")
                return []
            except Exception as e:
                self.logger.error(f"Error fetching user media: {e}")
                return []
            
            media_data = []
            for media in media_items:
                self.random_delay()
                try:
                    media_info = {
                        'id': media.id,
                        'code': media.code,
                        'taken_at': media.taken_at.isoformat(),
                        'media_type': media.media_type,
                        'caption': media.caption_text if media.caption_text else '',
                        'like_count': media.like_count,
                        'comment_count': media.comment_count,
                        'url': media.thumbnail_url,
                        'scraped_at': datetime.now().isoformat()
                    }
                    media_data.append(media_info)
                except ValidationError as ve:
                    self.logger.warning(f"Skipping media due to validation error: {ve}")
                    continue
                except Exception as e:
                    self.logger.warning(f"Skipping media due to error: {e}")
                    continue
            
            return media_data
        except Exception as e:
            self.logger.error(f"Error getting user media: {e}")
            return []
    
    def get_media_comments(self, media_id: str, count: int = 50) -> List[Dict]:
        """Get comments from a media post"""
        try:
            if not self.logged_in:
                self.logger.error("Not logged in")
                return []
            
            self.random_delay()
            comments = self.handle_rate_limit(self.client.media_comments, media_id, count)
            
            comment_data = []
            for comment in comments:
                comment_info = {
                    'id': comment.pk,
                    'user_id': comment.user.pk,
                    'username': comment.user.username,
                    'text': comment.text,
                    'created_at': comment.created_at.isoformat(),
                    'like_count': comment.like_count,
                    'scraped_at': datetime.now().isoformat()
                }
                comment_data.append(comment_info)
            
            return comment_data
        except Exception as e:
            self.logger.error(f"Error getting media comments: {e}")
            return []
    
    def get_hashtag_media(self, hashtag: str, count: int = 20) -> List[Dict]:
        """Get media posts from a hashtag"""
        from pydantic import ValidationError
        try:
            if not self.logged_in:
                self.logger.error("Not logged in")
                return []
            
            self.random_delay()
            try:
                media_items = self.handle_rate_limit(self.client.hashtag_medias_recent, hashtag, count)
            except ValidationError as ve:
                self.logger.warning(f"Validation error in hashtag_medias_recent call: {ve}")
                return []
            except Exception as e:
                self.logger.error(f"Error fetching hashtag media: {e}")
                return []
            
            media_data = []
            for media in media_items:
                self.random_delay()
                try:
                    media_info = {
                        'id': media.id,
                        'code': media.code,
                        'taken_at': media.taken_at.isoformat(),
                        'media_type': media.media_type,
                        'caption': media.caption_text if media.caption_text else '',
                        'like_count': media.like_count,
                        'comment_count': media.comment_count,
                        'user_id': media.user.pk,
                        'username': media.user.username,
                        'url': media.thumbnail_url,
                        'scraped_at': datetime.now().isoformat()
                    }
                    media_data.append(media_info)
                except ValidationError as ve:
                    self.logger.warning(f"Skipping media due to validation error: {ve}")
                    continue
                except Exception as e:
                    self.logger.warning(f"Skipping media due to error: {e}")
                    continue
            
            return media_data
        except Exception as e:
            self.logger.error(f"Error getting hashtag media: {e}")
            return []
    
    def search_users(self, query: str, count: int = 10) -> List[Dict]:
        """Search for users"""
        try:
            if not self.logged_in:
                self.logger.error("Not logged in")
                return []
            
            self.random_delay()
            users = self.handle_rate_limit(self.client.search_users, query)
            
            user_data = []
            for user in users:
                user_info = {
                    'user_id': user.pk,
                    'username': user.username,
                    'full_name': user.full_name,
                    'is_private': user.is_private,
                    'profile_pic_url': str(user.profile_pic_url),
                    'scraped_at': datetime.now().isoformat()
                }
                user_data.append(user_info)
            
            return user_data
        except Exception as e:
            self.logger.error(f"Error searching users: {e}")
            return []
    
    def save_data(self, data: Any, filename: str):
        """Save scraped data to JSON file"""
        from pydantic import HttpUrl
        def default_serializer(obj):
            if isinstance(obj, HttpUrl):
                return str(obj)
            if hasattr(obj, 'isoformat'):
                return obj.isoformat()
            return str(obj)
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=default_serializer)
            self.logger.info(f"Data saved to {filename}")
        except Exception as e:
            self.logger.error(f"Error saving data: {e}")
    
    def logout(self):
        """Logout from Instagram"""
        try:
            if self.logged_in:
                self.client.logout()
                self.logged_in = False
                self.logger.info("Logged out successfully")
        except Exception as e:
            self.logger.error(f"Error during logout: {e}")

# Example usage
def main():
    # Load environment variables from .env file
    load_dotenv()
    
    # Configuration
    USERNAME = os.getenv("INSTAGRAM_USERNAME")
    PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
    
    if not USERNAME or not PASSWORD:
        print("Error: Please set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your .env file.")
        return
    
    # Initialize scraper
    scraper = InstagramScraper(
        username=USERNAME,
        password=PASSWORD,
        session_file="session.json",
        delay_range=(5, 10)  # 5-10 second delays
    )
    
    try:
        # Clear any existing session to avoid CSRF issues
        scraper.clear_session()
        
        # Login
        if not scraper.login():
            print("Login failed!")
            return
        
        print("Login successful! Starting scraping...")
        
        # Example: Get user info
        user_info = scraper.get_user_info("instagram")
        if user_info:
            scraper.save_data(user_info, "user_info.json")
            print("User info scraped successfully")
        
        # Example: Get user media
        media_data = scraper.get_user_media("instagram", count=10)
        scraper.save_data(media_data, "user_media.json")
        if media_data:
            print(f"User media scraped successfully - {len(media_data)} items")
        else:
            print("User media scraping completed but no valid data found")
        
        # Example: Get hashtag media
        hashtag_media = scraper.get_hashtag_media("python", count=5)
        scraper.save_data(hashtag_media, "hashtag_media.json")
        if hashtag_media:
            print(f"Hashtag media scraped successfully - {len(hashtag_media)} items")
        else:
            print("Hashtag media scraping completed but no valid data found")
        
        # Example: Search users
        users = scraper.search_users("python", count=5)
        if users:
            scraper.save_data(users, "search_users.json")
            print("User search completed successfully")
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        scraper.logout()

if __name__ == "__main__":
    main()