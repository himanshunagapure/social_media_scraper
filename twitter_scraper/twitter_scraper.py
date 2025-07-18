import asyncio
import json
import logging
import os
import random
import time
from contextlib import aclosing
from datetime import datetime
from typing import Dict, List, Optional, Union
import aiofiles
import httpx
from twscrape import API, gather
from twscrape.logger import set_log_level
from fake_useragent import UserAgent
from dotenv import load_dotenv

class TwitterScraper:
    """
    Advanced Twitter scraper with security features and rate limiting
    """
    
    def __init__(self, db_path: str = "accounts.db", proxy: str = None, 
                 log_level: str = "INFO", config_file: str = "scraper_config.json"):
        """
        Initialize the Twitter scraper
        
        Args:
            db_path: Path to accounts database
            proxy: Proxy string (optional)
            log_level: Logging level
            config_file: Configuration file path
        """
        self.db_path = db_path
        self.proxy = proxy
        self.config_file = config_file
        self.api = None
        self.ua = UserAgent()
        self.session_cache = {}
        
        # Setup logging
        self.setup_logging(log_level)
        
        # Load configuration
        self.config = self.load_config()
        
        # Rate limiting settings
        self.request_count = 0
        self.last_request_time = 0
        self.min_delay = self.config.get("min_delay", 5)
        self.max_delay = self.config.get("max_delay", 10)
        self.max_requests_per_hour = self.config.get("max_requests_per_hour", 100)
        
        # Initialize API
        self.initialize_api()
    
    def setup_logging(self, log_level: str):
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('twitter_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        set_log_level(log_level)
    
    def load_config(self) -> Dict:
        """Load configuration from JSON file"""
        default_config = {
            "min_delay": 5,
            "max_delay": 10,
            "max_requests_per_hour": 100,
            "retry_attempts": 3,
            "retry_delay": 30,
            "user_agents": [],
            "proxies": [],
            "accounts": []
        }
        
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                self.logger.error(f"Error loading config: {e}")
        
        return default_config
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
    
    def initialize_api(self):
        """Initialize the Twitter API with proxy support"""
        try:
            self.api = API(self.db_path, proxy=self.proxy)
            self.logger.info("API initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize API: {e}")
            raise
    
    async def add_account(self, username: str, password: str, email: str, 
                         email_password: str, cookies: str = None, proxy: str = None):
        """
        Add a new account to the pool
        
        Args:
            username: Twitter username
            password: Twitter password
            email: Email address
            email_password: Email password for verification
            cookies: Account cookies (optional but recommended)
            proxy: Account-specific proxy (optional)
        """
        try:
            if cookies:
                await self.api.pool.add_account(username, password, email, 
                                               email_password, cookies=cookies, proxy=proxy)
                self.logger.info(f"Account {username} added with cookies")
            else:
                await self.api.pool.add_account(username, password, email, 
                                               email_password, proxy=proxy)
                self.logger.info(f"Account {username} added for login")
        except Exception as e:
            self.logger.error(f"Failed to add account {username}: {e}")
            raise
    
    async def login_accounts(self):
        """Login all accounts and cache sessions"""
        try:
            await self.api.pool.login_all()
            self.logger.info("All accounts logged in successfully")
            
            # Await 'get_all()' to retrieve all accounts
            accounts = await self.api.pool.get_all()
            for account in accounts:
                if hasattr(account, 'active') and account.active:
                    self.session_cache[account.username] = {
                        'logged_in': getattr(account, 'logged_in', None),
                        'last_used': getattr(account, 'last_used', None),
                        'total_requests': getattr(account, 'total_req', None)
                    }
        except Exception as e:
            self.logger.error(f"Failed to login accounts: {e}")
            raise
    
    def get_random_user_agent(self) -> str:
        """Get a random user agent"""
        if self.config.get("user_agents"):
            return random.choice(self.config["user_agents"])
        return self.ua.random
    
    def get_random_proxy(self) -> str:
        """Get a random proxy from config"""
        if self.config.get("proxies"):
            return random.choice(self.config["proxies"])
        return None
    
    async def rate_limit_delay(self):
        """Apply rate limiting with random delays"""
        current_time = time.time()
        
        # Check requests per hour limit
        if self.request_count >= self.max_requests_per_hour:
            if current_time - self.last_request_time < 3600:  # 1 hour
                wait_time = 3600 - (current_time - self.last_request_time)
                self.logger.warning(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                await asyncio.sleep(wait_time)
                self.request_count = 0
        
        # Apply random delay between requests
        delay = random.uniform(self.min_delay, self.max_delay)
        self.logger.debug(f"Applying delay: {delay:.2f} seconds")
        await asyncio.sleep(delay)
        
        self.request_count += 1
        self.last_request_time = current_time
    
    async def handle_errors(self, func, *args, **kwargs):
        """Handle errors with retry logic"""
        for attempt in range(self.config.get("retry_attempts", 3)):
            try:
                await self.rate_limit_delay()
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self.config.get("retry_attempts", 3) - 1:
                    retry_delay = self.config.get("retry_delay", 30)
                    self.logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    self.logger.error(f"All retry attempts failed for {func.__name__}")
                    raise
    
    async def search_tweets(self, query: str, limit: int = 100, 
                           product: str = "Latest") -> List[Dict]:
        """
        Search for tweets with error handling and rate limiting
        
        Args:
            query: Search query
            limit: Maximum number of tweets to return
            product: Search product type (Top, Latest, Media)
        
        Returns:
            List of tweet dictionaries
        """
        tweets = []
        
        try:
            self.logger.info(f"Searching for tweets: '{query}' (limit: {limit})")
            
            async def search_func():
                return await gather(
                    self.api.search(query, limit=limit, kv={"product": product})
                )
            
            results = await self.handle_errors(search_func)
            
            def get_media_url(media):
                return (
                    getattr(media, 'fullUrl',
                        getattr(media, 'media_url',
                            getattr(media, 'media_url_https',
                                getattr(media, 'url', None)
                            )
                        )
                    )
                )
            
            for tweet in results:
                tweets.append({
                    'id': tweet.id,
                    'username': tweet.user.username,
                    'display_name': tweet.user.displayname,
                    'content': tweet.rawContent,
                    'created_at': tweet.date.isoformat() if tweet.date else None,
                    'retweet_count': tweet.retweetCount,
                    'like_count': tweet.likeCount,
                    'reply_count': tweet.replyCount,
                    'quote_count': tweet.quoteCount,
                    'lang': tweet.lang,
                    'url': tweet.url,
                    # Robust media extraction
                    'media': (
                        [get_media_url(media) for media in tweet.media] if isinstance(tweet.media, (list, tuple))
                        else ([get_media_url(tweet.media)] if tweet.media else [])
                    ),
                    'hashtags': tweet.hashtags,
                    # Fix: convert mentionedUsers to usernames for JSON serialization
                    'mentions': [u.username for u in tweet.mentionedUsers] if tweet.mentionedUsers else []
                })
            
            self.logger.info(f"Successfully retrieved {len(tweets)} tweets")
            return tweets
            
        except Exception as e:
            self.logger.error(f"Error searching tweets: {e}")
            raise
    
    async def get_user_info(self, username: str) -> Dict:
        """
        Get user information
        
        Args:
            username: Twitter username
        
        Returns:
            User information dictionary
        """
        try:
            self.logger.info(f"Getting user info for: {username}")
            
            async def user_func():
                return await self.api.user_by_login(username)
            
            user = await self.handle_errors(user_func)
            
            return {
                'id': user.id,
                'username': user.username,
                'display_name': user.displayname,
                'description': user.rawDescription,  # <-- updated here
                'followers_count': user.followersCount,
                'following_count': user.friendsCount,
                'tweets_count': user.statusesCount,
                'likes_count': user.favouritesCount,
                'created_at': user.created.isoformat() if user.created else None,
                'verified': user.verified,
                'profile_image_url': user.profileImageUrl,
                'profile_banner_url': user.profileBannerUrl,
                'location': user.location,
                'url': user.url
            }
            
        except Exception as e:
            self.logger.error(f"Error getting user info: {e}")
            raise
    
    async def get_user_tweets(self, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Get user's tweets
        
        Args:
            user_id: Twitter user ID
            limit: Maximum number of tweets to return
        
        Returns:
            List of tweet dictionaries
        """
        tweets = []
        
        try:
            self.logger.info(f"Getting tweets for user ID: {user_id}")
            
            async def tweets_func():
                return await gather(self.api.user_tweets(user_id, limit=limit))
            
            results = await self.handle_errors(tweets_func)
            
            def get_media_url(media):
                return (
                    getattr(media, 'fullUrl',
                        getattr(media, 'media_url',
                            getattr(media, 'media_url_https',
                                getattr(media, 'url', None)
                            )
                        )
                    )
                )
            
            for tweet in results:
                tweets.append({
                    'id': tweet.id,
                    'content': tweet.rawContent,
                    'created_at': tweet.date.isoformat() if tweet.date else None,
                    'retweet_count': tweet.retweetCount,
                    'like_count': tweet.likeCount,
                    'reply_count': tweet.replyCount,
                    'quote_count': tweet.quoteCount,
                    'lang': tweet.lang,
                    'url': tweet.url,
                    # Robust media extraction
                    'media': (
                        [get_media_url(media) for media in tweet.media] if isinstance(tweet.media, (list, tuple))
                        else ([get_media_url(tweet.media)] if tweet.media else [])
                    )
                })
            
            self.logger.info(f"Successfully retrieved {len(tweets)} user tweets")
            return tweets
            
        except Exception as e:
            self.logger.error(f"Error getting user tweets: {e}")
            raise
    
    async def get_followers(self, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Get user's followers
        
        Args:
            user_id: Twitter user ID
            limit: Maximum number of followers to return
        
        Returns:
            List of follower dictionaries
        """
        followers = []
        
        try:
            self.logger.info(f"Getting followers for user ID: {user_id}")
            
            async def followers_func():
                return await gather(self.api.followers(user_id, limit=limit))
            
            results = await self.handle_errors(followers_func)
            
            for follower in results:
                followers.append({
                    'id': follower.id,
                    'username': follower.username,
                    'display_name': follower.displayname,
                    'followers_count': follower.followersCount,
                    'following_count': follower.friendsCount,
                    'verified': follower.verified,
                    'profile_image_url': follower.profileImageUrl
                })
            
            self.logger.info(f"Successfully retrieved {len(followers)} followers")
            return followers
            
        except Exception as e:
            self.logger.error(f"Error getting followers: {e}")
            raise
    
    async def save_to_json(self, data: Union[List, Dict], filename: str):
        """
        Save data to JSON file asynchronously
        
        Args:
            data: Data to save
            filename: Output filename
        """
        try:
            async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(data, indent=2, ensure_ascii=False))
            self.logger.info(f"Data saved to {filename}")
        except Exception as e:
            self.logger.error(f"Error saving to JSON: {e}")
            raise
    
    async def export_to_csv(self, data: List[Dict], filename: str):
        """
        Export data to CSV file
        
        Args:
            data: List of dictionaries to export
            filename: Output filename
        """
        try:
            import pandas as pd
            df = pd.DataFrame(data)
            df.to_csv(filename, index=False, encoding='utf-8')
            self.logger.info(f"Data exported to {filename}")
        except Exception as e:
            self.logger.error(f"Error exporting to CSV: {e}")
            raise
    
    def get_account_stats(self):
        """Get account statistics"""
        try:
            stats = {}
            for username, session in self.session_cache.items():
                stats[username] = {
                    'logged_in': session['logged_in'],
                    'last_used': session['last_used'],
                    'total_requests': session['total_requests']
                }
            return stats
        except Exception as e:
            self.logger.error(f"Error getting account stats: {e}")
            return {}
    
    async def close(self):
        """Close the scraper and clean up resources"""
        try:
            if self.api:
                # Close any open connections
                self.logger.info("Closing scraper resources")
            self.save_config()
        except Exception as e:
            self.logger.error(f"Error closing scraper: {e}")


# Example usage and testing
async def main():
    """Example usage of the Twitter scraper"""
    
    # Load environment variables from .env file
    load_dotenv()
    TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
    TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")
    TWITTER_EMAIL = os.getenv("TWITTER_EMAIL")
    TWITTER_EMAIL_PASSWORD = os.getenv("TWITTER_EMAIL_PASSWORD")
    TWITTER_COOKIES = "ct0=b07633d53ff2c5ed19fb96f06bc0bda3e3f94a306649c11efcd65a00a947aac76e4c88bd70b01db4b0e5966719529c94203c4403518796f8a20d014f6df414e6494e666506eb9b0384124310aa665cf8; auth_token=cce8b6a5da2deabf14823796bc6bf05743d0fdb1; personalization_id=v1_YVrwks4LK+PiTh2HXQdeCg=="

    if not all([TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_EMAIL, TWITTER_EMAIL_PASSWORD]):
        print("Error: Please set TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_EMAIL, and TWITTER_EMAIL_PASSWORD in your .env file.")
        return
    # Initialize scraper
    scraper = TwitterScraper(
        db_path="accounts.db",
        proxy=None,  # Add proxy if needed
        log_level="INFO"
    )
    
    try:
        # Add accounts (use cookies for better stability)
        # Example with cookies (recommended):
        await scraper.add_account(
            TWITTER_USERNAME,
            TWITTER_PASSWORD,
            TWITTER_EMAIL,
            TWITTER_EMAIL_PASSWORD,
            cookies=TWITTER_COOKIES
        )
        #Example without cookies (less stable):
        #await scraper.add_account("zeref_first", "Movies@first$123", "moviesfirst114@gmail.com", 
        #                         "Movies@first$123")
        
        #Login all accounts
        await scraper.login_accounts()
        
        # Search for tweets
        tweets = await scraper.search_tweets("python programming", limit=10)
        await scraper.save_to_json(tweets, "python_tweets.json")
        
        # Get user information
        user_info = await scraper.get_user_info("elonmusk")
        print(f"User info: {user_info}")
        
        # Get user tweets
        user_tweets = await scraper.get_user_tweets(user_info['id'], limit=10)
        await scraper.save_to_json(user_tweets, "user_tweets.json")
        
        # Get followers
        followers = await scraper.get_followers(user_info['id'], limit=10)
        await scraper.save_to_json(followers, "followers.json")
        
        # Export to CSV
        await scraper.export_to_csv(tweets, "tweets.csv")
        
        # Get account statistics
        stats = scraper.get_account_stats()
        print(f"Account stats: {stats}")
        
    except Exception as e:
        print(f"Error in main: {e}")
        
    finally:
        await scraper.close()


if __name__ == "__main__":
    # Run the scraper
    asyncio.run(main())