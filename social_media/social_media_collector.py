# Social Media Data Collector
# Complete system for collecting data from Reddit and YouTube

import os
import time
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod
import asyncio
import aiohttp
from urllib.parse import urlencode

# Third-party imports (install with: pip install praw google-api-python-client python-dotenv requests)
import praw
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('social_media_collector.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Data Models
@dataclass
class SocialMediaPost:
    """Base class for social media posts"""
    id: str
    platform: str
    title: str
    content: str
    author: str
    created_at: datetime
    url: str
    score: int = 0
    comments_count: int = 0
    metadata: Dict[str, Any] = None

@dataclass
class RedditPost(SocialMediaPost):
    """Reddit-specific post data"""
    subreddit: str = ""
    upvotes: int = 0
    downvotes: int = 0
    gilded: int = 0
    
@dataclass
class YouTubeVideo(SocialMediaPost):
    """YouTube-specific video data"""
    channel_id: str = ""
    channel_title: str = ""
    view_count: int = 0
    like_count: int = 0
    duration: str = ""
    tags: List[str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = []

# Database Manager
class DatabaseManager:
    """Handles all database operations"""
    
    def __init__(self, db_path: str = "social_media_data.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Posts table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    title TEXT,
                    content TEXT,
                    author TEXT,
                    created_at TIMESTAMP,
                    url TEXT,
                    score INTEGER DEFAULT 0,
                    comments_count INTEGER DEFAULT 0,
                    metadata TEXT,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Reddit-specific table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reddit_posts (
                    id TEXT PRIMARY KEY,
                    subreddit TEXT,
                    upvotes INTEGER,
                    downvotes INTEGER,
                    gilded INTEGER,
                    FOREIGN KEY (id) REFERENCES posts (id)
                )
            ''')
            
            # YouTube-specific table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS youtube_videos (
                    id TEXT PRIMARY KEY,
                    channel_id TEXT,
                    channel_title TEXT,
                    view_count INTEGER,
                    like_count INTEGER,
                    duration TEXT,
                    tags TEXT,
                    FOREIGN KEY (id) REFERENCES posts (id)
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_platform ON posts(platform)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON posts(created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_subreddit ON reddit_posts(subreddit)')
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def save_post(self, post: SocialMediaPost):
        """Save a post to the database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert into posts table
                cursor.execute('''
                    INSERT OR REPLACE INTO posts 
                    (id, platform, title, content, author, created_at, url, score, comments_count, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    post.id, post.platform, post.title, post.content, post.author,
                    post.created_at, post.url, post.score, post.comments_count,
                    json.dumps(post.metadata) if post.metadata else None
                ))
                
                # Insert platform-specific data
                if isinstance(post, RedditPost):
                    cursor.execute('''
                        INSERT OR REPLACE INTO reddit_posts 
                        (id, subreddit, upvotes, downvotes, gilded)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (post.id, post.subreddit, post.upvotes, post.downvotes, post.gilded))
                
                elif isinstance(post, YouTubeVideo):
                    cursor.execute('''
                        INSERT OR REPLACE INTO youtube_videos 
                        (id, channel_id, channel_title, view_count, like_count, duration, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (post.id, post.channel_id, post.channel_title, post.view_count, 
                          post.like_count, post.duration, json.dumps(post.tags)))
                
                conn.commit()
                logger.info(f"Saved post {post.id} from {post.platform}")
        
        except sqlite3.Error as e:
            logger.error(f"Database error saving post {post.id}: {e}")
    
    def get_posts(self, platform: str = None, limit: int = 100) -> List[Dict]:
        """Retrieve posts from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM posts"
                params = []
                
                if platform:
                    query += " WHERE platform = ?"
                    params.append(platform)
                
                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                columns = [description[0] for description in cursor.description]
                
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving posts: {e}")
            return []

# Base Collector Class
class BaseCollector(ABC):
    """Abstract base class for social media collectors"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.rate_limit_delay = 1  # seconds between requests
    
    @abstractmethod
    def collect(self, query: str, limit: int = 100) -> List[SocialMediaPost]:
        """Collect posts from the platform"""
        pass
    
    def rate_limit(self):
        """Simple rate limiting"""
        time.sleep(self.rate_limit_delay)

# Reddit Collector
class RedditCollector(BaseCollector):
    """Collects data from Reddit using PRAW"""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager)
        self.reddit = self._init_reddit_client()
        self.rate_limit_delay = 1  # Reddit allows 60 requests per minute
    
    def _init_reddit_client(self):
        """Initialize Reddit client"""
        try:
            reddit = praw.Reddit(
                client_id=os.getenv('REDDIT_CLIENT_ID'),
                client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
                user_agent=os.getenv('REDDIT_USER_AGENT', 'SocialMediaCollector/1.0')
            )
            logger.info("Reddit client initialized successfully")
            return reddit
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise
    
    def collect(self, query: str, limit: int = 100) -> List[RedditPost]:
        """Collect posts from Reddit"""
        posts = []
        
        try:
            # Search across all subreddits
            search_results = self.reddit.subreddit('all').search(query, limit=limit)
            
            for submission in search_results:
                self.rate_limit()
                
                # Convert Reddit submission to RedditPost
                post = RedditPost(
                    id=submission.id,
                    platform='reddit',
                    title=submission.title,
                    content=submission.selftext,
                    author=str(submission.author) if submission.author else '[deleted]',
                    created_at=datetime.fromtimestamp(submission.created_utc),
                    url=f"https://reddit.com{submission.permalink}",
                    score=submission.score,
                    comments_count=submission.num_comments,
                    subreddit=submission.subreddit.display_name,
                    upvotes=submission.ups,
                    downvotes=submission.downs,
                    gilded=submission.gilded,
                    metadata={
                        'is_self': submission.is_self,
                        'nsfw': submission.over_18,
                        'spoiler': submission.spoiler,
                        'locked': submission.locked,
                        'archived': submission.archived
                    }
                )
                
                posts.append(post)
                self.db_manager.save_post(post)
                logger.info(f"Collected Reddit post: {post.title[:50]}...")
            
            logger.info(f"Collected {len(posts)} Reddit posts for query: {query}")
            
        except Exception as e:
            logger.error(f"Error collecting Reddit posts: {e}")
        
        return posts
    
    def collect_subreddit(self, subreddit_name: str, limit: int = 100, sort: str = 'hot') -> List[RedditPost]:
        """Collect posts from a specific subreddit"""
        posts = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get posts based on sort method
            if sort == 'hot':
                submissions = subreddit.hot(limit=limit)
            elif sort == 'new':
                submissions = subreddit.new(limit=limit)
            elif sort == 'top':
                submissions = subreddit.top(limit=limit)
            else:
                submissions = subreddit.hot(limit=limit)
            
            for submission in submissions:
                self.rate_limit()
                
                post = RedditPost(
                    id=submission.id,
                    platform='reddit',
                    title=submission.title,
                    content=submission.selftext,
                    author=str(submission.author) if submission.author else '[deleted]',
                    created_at=datetime.fromtimestamp(submission.created_utc),
                    url=f"https://reddit.com{submission.permalink}",
                    score=submission.score,
                    comments_count=submission.num_comments,
                    subreddit=submission.subreddit.display_name,
                    upvotes=submission.ups,
                    downvotes=submission.downs,
                    gilded=submission.gilded,
                    metadata={
                        'is_self': submission.is_self,
                        'nsfw': submission.over_18,
                        'spoiler': submission.spoiler,
                        'locked': submission.locked,
                        'archived': submission.archived
                    }
                )
                
                posts.append(post)
                self.db_manager.save_post(post)
                logger.info(f"Collected Reddit post from r/{subreddit_name}: {post.title[:50]}...")
            
            logger.info(f"Collected {len(posts)} posts from r/{subreddit_name}")
            
        except Exception as e:
            logger.error(f"Error collecting from subreddit {subreddit_name}: {e}")
        
        return posts

# YouTube Collector
class YouTubeCollector(BaseCollector):
    """Collects data from YouTube using YouTube Data API"""
    
    def __init__(self, db_manager: DatabaseManager):
        super().__init__(db_manager)
        self.youtube = self._init_youtube_client()
        self.rate_limit_delay = 0.1  # YouTube has generous rate limits
    
    def _init_youtube_client(self):
        """Initialize YouTube client"""
        try:
            youtube = build('youtube', 'v3', 
                          developerKey=os.getenv('YOUTUBE_API_KEY'))
            logger.info("YouTube client initialized successfully")
            return youtube
        except Exception as e:
            logger.error(f"Failed to initialize YouTube client: {e}")
            raise
    
    def collect(self, query: str, limit: int = 100) -> List[YouTubeVideo]:
        """Collect videos from YouTube"""
        videos = []
        
        try:
            # Search for videos
            search_request = self.youtube.search().list(
                q=query,
                part='snippet',
                type='video',
                maxResults=min(limit, 50)  # YouTube max is 50 per request
            )
            
            search_response = search_request.execute()
            
            # Get video IDs
            video_ids = [item['id']['videoId'] for item in search_response['items']]
            
            # Get detailed video information
            videos_request = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                id=','.join(video_ids)
            )
            
            videos_response = videos_request.execute()
            
            for video_data in videos_response['items']:
                self.rate_limit()
                
                snippet = video_data['snippet']
                statistics = video_data.get('statistics', {})
                content_details = video_data.get('contentDetails', {})
                
                video = YouTubeVideo(
                    id=video_data['id'],
                    platform='youtube',
                    title=snippet['title'],
                    content=snippet['description'],
                    author=snippet['channelTitle'],
                    created_at=datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00')),
                    url=f"https://youtube.com/watch?v={video_data['id']}",
                    score=int(statistics.get('likeCount', 0)),
                    comments_count=int(statistics.get('commentCount', 0)),
                    channel_id=snippet['channelId'],
                    channel_title=snippet['channelTitle'],
                    view_count=int(statistics.get('viewCount', 0)),
                    like_count=int(statistics.get('likeCount', 0)),
                    duration=content_details.get('duration', ''),
                    tags=snippet.get('tags', []),
                    metadata={
                        'category_id': snippet.get('categoryId'),
                        'default_language': snippet.get('defaultLanguage'),
                        'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                        'dislike_count': statistics.get('dislikeCount', 0)
                    }
                )
                
                videos.append(video)
                self.db_manager.save_post(video)
                logger.info(f"Collected YouTube video: {video.title[:50]}...")
            
            logger.info(f"Collected {len(videos)} YouTube videos for query: {query}")
            
        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
        except Exception as e:
            logger.error(f"Error collecting YouTube videos: {e}")
        
        return videos
    
    def collect_channel(self, channel_id: str, limit: int = 100) -> List[YouTubeVideo]:
        """Collect videos from a specific YouTube channel"""
        videos = []
        
        try:
            # Get channel's uploads playlist
            channel_request = self.youtube.channels().list(
                part='contentDetails',
                id=channel_id
            )
            
            channel_response = channel_request.execute()
            
            if not channel_response['items']:
                logger.warning(f"Channel {channel_id} not found")
                return videos
            
            uploads_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # Get videos from uploads playlist
            playlist_request = self.youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=min(limit, 50)
            )
            
            playlist_response = playlist_request.execute()
            
            # Get video IDs
            video_ids = [item['snippet']['resourceId']['videoId'] for item in playlist_response['items']]
            
            # Get detailed video information
            videos_request = self.youtube.videos().list(
                part='snippet,statistics,contentDetails',
                id=','.join(video_ids)
            )
            
            videos_response = videos_request.execute()
            
            for video_data in videos_response['items']:
                self.rate_limit()
                
                snippet = video_data['snippet']
                statistics = video_data.get('statistics', {})
                content_details = video_data.get('contentDetails', {})
                
                video = YouTubeVideo(
                    id=video_data['id'],
                    platform='youtube',
                    title=snippet['title'],
                    content=snippet['description'],
                    author=snippet['channelTitle'],
                    created_at=datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00')),
                    url=f"https://youtube.com/watch?v={video_data['id']}",
                    score=int(statistics.get('likeCount', 0)),
                    comments_count=int(statistics.get('commentCount', 0)),
                    channel_id=snippet['channelId'],
                    channel_title=snippet['channelTitle'],
                    view_count=int(statistics.get('viewCount', 0)),
                    like_count=int(statistics.get('likeCount', 0)),
                    duration=content_details.get('duration', ''),
                    tags=snippet.get('tags', []),
                    metadata={
                        'category_id': snippet.get('categoryId'),
                        'default_language': snippet.get('defaultLanguage'),
                        'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url')
                    }
                )
                
                videos.append(video)
                self.db_manager.save_post(video)
                logger.info(f"Collected video from channel: {video.title[:50]}...")
            
            logger.info(f"Collected {len(videos)} videos from channel {channel_id}")
            
        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
        except Exception as e:
            logger.error(f"Error collecting from channel {channel_id}: {e}")
        
        return videos

# Main Collector Class
class SocialMediaCollector:
    """Main class that orchestrates all collectors"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.reddit_collector = RedditCollector(self.db_manager)
        self.youtube_collector = YouTubeCollector(self.db_manager)
    
    def collect_all(self, query: str, platforms: List[str] = None, limit: int = 100) -> Dict[str, List[SocialMediaPost]]:
        """Collect data from all specified platforms"""
        if platforms is None:
            platforms = ['reddit', 'youtube']
        
        results = {}
        
        if 'reddit' in platforms:
            logger.info(f"Collecting Reddit posts for: {query}")
            results['reddit'] = self.reddit_collector.collect(query, limit)
        
        if 'youtube' in platforms:
            logger.info(f"Collecting YouTube videos for: {query}")
            results['youtube'] = self.youtube_collector.collect(query, limit)
        
        return results
    
    def collect_reddit_subreddit(self, subreddit: str, limit: int = 100, sort: str = 'hot') -> List[RedditPost]:
        """Collect posts from a specific subreddit"""
        return self.reddit_collector.collect_subreddit(subreddit, limit, sort)
    
    def collect_youtube_channel(self, channel_id: str, limit: int = 100) -> List[YouTubeVideo]:
        """Collect videos from a specific YouTube channel"""
        return self.youtube_collector.collect_channel(channel_id, limit)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get collection statistics"""
        stats = {}
        
        with sqlite3.connect(self.db_manager.db_path) as conn:
            cursor = conn.cursor()
            
            # Overall stats
            cursor.execute("SELECT COUNT(*) FROM posts")
            stats['total_posts'] = cursor.fetchone()[0]
            
            # Platform breakdown
            cursor.execute("SELECT platform, COUNT(*) FROM posts GROUP BY platform")
            platform_stats = cursor.fetchall()
            stats['by_platform'] = {platform: count for platform, count in platform_stats}
            
            # Recent activity (last 24 hours)
            cursor.execute("""
                SELECT platform, COUNT(*) 
                FROM posts 
                WHERE collected_at > datetime('now', '-1 day')
                GROUP BY platform
            """)
            recent_stats = cursor.fetchall()
            stats['recent_24h'] = {platform: count for platform, count in recent_stats}
        
        return stats

# Configuration and Setup
def setup_environment():
    """Setup environment variables and configurations"""
    required_vars = [
        'REDDIT_CLIENT_ID',
        'REDDIT_CLIENT_SECRET',
        'YOUTUBE_API_KEY'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.info("Please create a .env file with the following variables:")
        logger.info("REDDIT_CLIENT_ID=your_reddit_client_id")
        logger.info("REDDIT_CLIENT_SECRET=your_reddit_client_secret")
        logger.info("REDDIT_USER_AGENT=YourApp/1.0")
        logger.info("YOUTUBE_API_KEY=your_youtube_api_key")
        return False
    
    return True

# Example usage and main function
def main():
    """Main function with example usage"""
    if not setup_environment():
        return
    
    # Initialize the collector
    collector = SocialMediaCollector()
    
    try:
        # Example 1: Search across both platforms
        print("=== Searching for 'artificial intelligence' across platforms ===")
        results = collector.collect_all('artificial intelligence', limit=10)
        
        for platform, posts in results.items():
            print(f"\n{platform.upper()} Results ({len(posts)} posts):")
            for post in posts[:3]:  # Show first 3 posts
                print(f"  - {post.title[:60]}...")
                print(f"    Score: {post.score}, Comments: {post.comments_count}")
                print(f"    URL: {post.url}")
                print()
        
        # Example 2: Collect from specific subreddit
        print("\n=== Collecting from r/technology ===")
        tech_posts = collector.collect_reddit_subreddit('technology', limit=5)
        for post in tech_posts:
            print(f"  - {post.title[:60]}...")
            print(f"    Upvotes: {post.upvotes}, Comments: {post.comments_count}")
        
        # Example 3: Get statistics
        print("\n=== Collection Statistics ===")
        stats = collector.get_statistics()
        print(f"Total posts collected: {stats['total_posts']}")
        print("By platform:")
        for platform, count in stats['by_platform'].items():
            print(f"  {platform}: {count}")
        
        # Example 4: Retrieve stored posts
        print("\n=== Recent Reddit Posts from Database ===")
        reddit_posts = collector.db_manager.get_posts(platform='reddit', limit=5)
        for post in reddit_posts:
            print(f"  - {post['title'][:60]}...")
            print(f"    Author: {post['author']}, Score: {post['score']}")
    
    except Exception as e:
        logger.error(f"Error in main execution: {e}")

if __name__ == "__main__":
    main()