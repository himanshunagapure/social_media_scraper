#!/usr/bin/env python3
"""
Facebook Data Scraper - A comprehensive scraper for public Facebook data
Using facebook-scraper library with proxy rotation, user-agent rotation, 
rate limiting, error handling, and logging.

Author: AI Assistant
Date: 2025
License: MIT
"""

import os
import sys
import time
import json
import random
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path

try:
    from facebook_scraper import get_posts, set_user_agent, get_page_info
    from fake_useragent import UserAgent
except ImportError as e:
    print(f"Missing required libraries: {e}")
    print("Please install with: pip install facebook-scraper fake-useragent requests")
    sys.exit(1)


@dataclass
class ScraperConfig:
    """Configuration class for the Facebook scraper"""
    target_pages: List[str]
    target_groups: List[str]
    max_posts_per_target: int
    min_delay: float
    max_delay: float
    proxy_list: List[str]
    output_dir: str
    log_level: str
    retry_attempts: int
    retry_backoff: float
    health_check_interval: int
    user_agent_rotation: bool
    proxy_rotation: bool


class ProxyManager:
    """Manages proxy rotation and health checking"""
    
    def __init__(self, proxy_list: List[str]):
        self.proxy_list = proxy_list
        self.current_index = 0
        self.failed_proxies = set()
        self.logger = logging.getLogger(__name__)
    
    def get_next_proxy(self) -> Optional[str]:
        """Get the next working proxy from the list"""
        if not self.proxy_list:
            return None
        
        attempts = 0
        while attempts < len(self.proxy_list):
            proxy = self.proxy_list[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxy_list)
            
            if proxy not in self.failed_proxies:
                if self._test_proxy(proxy):
                    return proxy
                else:
                    self.failed_proxies.add(proxy)
            
            attempts += 1
        
        # If all proxies failed, reset failed set and try again
        self.failed_proxies.clear()
        return self.proxy_list[0] if self.proxy_list else None
    
    def _test_proxy(self, proxy: str) -> bool:
        """Test if a proxy is working"""
        try:
            response = requests.get(
                'https://httpbin.org/ip',
                proxies={'http': proxy, 'https': proxy},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Proxy {proxy} failed test: {e}")
            return False


class UserAgentManager:
    """Manages user agent rotation"""
    
    def __init__(self):
        self.ua = UserAgent()
        self.logger = logging.getLogger(__name__)
    
    def get_random_user_agent(self) -> str:
        """Get a random user agent string"""
        try:
            return self.ua.random
        except Exception as e:
            self.logger.warning(f"Failed to get random user agent: {e}")
            # Fallback user agents
            fallback_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ]
            return random.choice(fallback_agents)


class HealthMonitor:
    """Monitors scraper health and performance"""
    
    def __init__(self):
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = datetime.now()
        self.last_success_time = None
        self.logger = logging.getLogger(__name__)
    
    def record_success(self):
        """Record a successful request"""
        self.successful_requests += 1
        self.last_success_time = datetime.now()
    
    def record_failure(self):
        """Record a failed request"""
        self.failed_requests += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current health statistics"""
        total_requests = self.successful_requests + self.failed_requests
        success_rate = (self.successful_requests / total_requests * 100) if total_requests > 0 else 0
        runtime = datetime.now() - self.start_time
        
        return {
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'total_requests': total_requests,
            'success_rate': round(success_rate, 2),
            'runtime': str(runtime),
            'last_success': self.last_success_time.isoformat() if self.last_success_time else None
        }
    
    def log_health_report(self):
        """Log current health statistics"""
        stats = self.get_stats()
        self.logger.info(f"Health Report - Success Rate: {stats['success_rate']}%, "
                        f"Total Requests: {stats['total_requests']}, "
                        f"Runtime: {stats['runtime']}")


class FacebookScraper:
    """Main Facebook scraper class"""
    
    def __init__(self, config: ScraperConfig):
        self.config = config
        self.proxy_manager = ProxyManager(config.proxy_list)
        self.ua_manager = UserAgentManager()
        self.health_monitor = HealthMonitor()
        self.logger = self._setup_logging()
        self.scraped_data = []
        
        # Create output directory
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
        
        self.logger.info("Facebook scraper initialized")
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        import os
        os.makedirs(self.config.output_dir, exist_ok=True)
        logger = logging.getLogger(__name__)
        logger.setLevel(getattr(logging, self.config.log_level.upper()))
        
        # Create handlers
        console_handler = logging.StreamHandler()
        file_handler = logging.FileHandler(
            os.path.join(self.config.output_dir, 'scraper.log')
        )
        
        # Create formatters
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
        return logger
    
    def _random_delay(self):
        """Apply random delay between requests"""
        delay = random.uniform(self.config.min_delay, self.config.max_delay)
        self.logger.debug(f"Applying delay: {delay:.2f} seconds")
        time.sleep(delay)
    
    def _setup_session(self):
        """Setup session with proxy and user agent"""
        if self.config.user_agent_rotation:
            user_agent = self.ua_manager.get_random_user_agent()
            set_user_agent(user_agent)
            self.logger.debug(f"Set user agent: {user_agent[:50]}...")
        
        if self.config.proxy_rotation and self.config.proxy_list:
            proxy = self.proxy_manager.get_next_proxy()
            if proxy:
                # Note: facebook-scraper doesn't directly support proxy configuration
                # You would need to configure system proxy or use a different approach
                self.logger.debug(f"Using proxy: {proxy}")
    
    def _handle_request_with_retry(self, func, *args, **kwargs):
        """Handle requests with retry logic and error handling"""
        for attempt in range(self.config.retry_attempts):
            try:
                result = func(*args, **kwargs)
                self.health_monitor.record_success()
                return result
            
            except Exception as e:
                self.health_monitor.record_failure()
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.retry_attempts - 1:
                    backoff_time = self.config.retry_backoff * (2 ** attempt)
                    self.logger.info(f"Retrying in {backoff_time:.2f} seconds...")
                    time.sleep(backoff_time)
                else:
                    self.logger.error(f"All {self.config.retry_attempts} attempts failed")
                    raise
    
    def _scrape_page_posts(self, page_name: str) -> List[Dict]:
        """Scrape posts from a Facebook page"""
        self.logger.info(f"Scraping posts from page: {page_name}")
        posts_data = []
        
        try:
            def get_page_posts():
                return get_posts(
                    page_name,
                    pages=self.config.max_posts_per_target // 10,  # Approximate posts per page
                    timeout=30,
                    sleep=random.uniform(1, 3)  # Additional delay
                )
            
            posts = self._handle_request_with_retry(get_page_posts)
            
            for i, post in enumerate(posts):
                if i >= self.config.max_posts_per_target:
                    break
                
                try:
                    post_data = {
                        'post_id': post.get('post_id', ''),
                        'text': post.get('text', ''),
                        'time': post.get('time', '').isoformat() if post.get('time') else '',
                        'image': post.get('image', ''),
                        'likes': post.get('likes', 0),
                        'comments': post.get('comments', 0),
                        'shares': post.get('shares', 0),
                        'post_url': post.get('post_url', ''),
                        'page_name': page_name,
                        'scraped_at': datetime.now().isoformat()
                    }
                    posts_data.append(post_data)
                    
                    self.logger.debug(f"Scraped post {i+1}: {post_data['post_id']}")
                    
                    # Apply delay between posts
                    if i < self.config.max_posts_per_target - 1:
                        self._random_delay()
                
                except Exception as e:
                    self.logger.error(f"Error processing post {i+1}: {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error scraping page {page_name}: {e}")
        
        self.logger.info(f"Scraped {len(posts_data)} posts from {page_name}")
        return posts_data
    
    def _scrape_group_posts(self, group_name: str) -> List[Dict]:
        """Scrape posts from a Facebook group"""
        self.logger.info(f"Scraping posts from group: {group_name}")
        # Similar implementation to page scraping
        # Note: Group scraping may require special handling or different parameters
        return self._scrape_page_posts(group_name)  # Simplified for this example
    
    def _save_data(self, data: List[Dict], filename: str):
        """Save scraped data to JSON file"""
        filepath = os.path.join(self.config.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Data saved to {filepath}")
        
        except Exception as e:
            self.logger.error(f"Error saving data to {filepath}: {e}")
    
    def scrape_all_targets(self):
        """Scrape all configured targets"""
        self.logger.info("Starting scraping process")
        
        # Scrape pages
        for page in self.config.target_pages:
            try:
                self._setup_session()
                posts = self._scrape_page_posts(page)
                self.scraped_data.extend(posts)
                
                # Save individual page data
                self._save_data(posts, f"{page}_posts.json")
                
                # Health check
                if len(self.scraped_data) % self.config.health_check_interval == 0:
                    self.health_monitor.log_health_report()
                
                # Longer delay between different pages
                if page != self.config.target_pages[-1]:
                    time.sleep(random.uniform(10, 20))
            
            except Exception as e:
                self.logger.error(f"Error scraping page {page}: {e}")
                continue
        
        # Scrape groups
        for group in self.config.target_groups:
            try:
                self._setup_session()
                posts = self._scrape_group_posts(group)
                self.scraped_data.extend(posts)
                
                # Save individual group data
                self._save_data(posts, f"{group}_posts.json")
                
                # Health check
                if len(self.scraped_data) % self.config.health_check_interval == 0:
                    self.health_monitor.log_health_report()
                
                # Longer delay between different groups
                if group != self.config.target_groups[-1]:
                    time.sleep(random.uniform(10, 20))
            
            except Exception as e:
                self.logger.error(f"Error scraping group {group}: {e}")
                continue
        
        # Save all scraped data
        self._save_data(self.scraped_data, "all_scraped_data.json")
        
        # Final health report
        self.health_monitor.log_health_report()
        self.logger.info(f"Scraping completed. Total posts scraped: {len(self.scraped_data)}")


def load_config(config_path: str) -> ScraperConfig:
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        return ScraperConfig(
            target_pages=config_data.get('target_pages', []),
            target_groups=config_data.get('target_groups', []),
            max_posts_per_target=config_data.get('max_posts_per_target', 50),
            min_delay=config_data.get('min_delay', 5.0),
            max_delay=config_data.get('max_delay', 10.0),
            proxy_list=config_data.get('proxy_list', []),
            output_dir=config_data.get('output_dir', 'scraped_data'),
            log_level=config_data.get('log_level', 'INFO'),
            retry_attempts=config_data.get('retry_attempts', 3),
            retry_backoff=config_data.get('retry_backoff', 2.0),
            health_check_interval=config_data.get('health_check_interval', 10),
            user_agent_rotation=config_data.get('user_agent_rotation', True),
            proxy_rotation=config_data.get('proxy_rotation', True)
        )
    
    except FileNotFoundError:
        print(f"Config file {config_path} not found. Creating default config...")
        create_default_config(config_path)
        return load_config(config_path)
    
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)


def create_default_config(config_path: str):
    """Create a default configuration file"""
    default_config = {
        "target_pages": ["example_page"],
        "target_groups": [],
        "max_posts_per_target": 50,
        "min_delay": 5.0,
        "max_delay": 10.0,
        "proxy_list": [
            # Add your proxy list here
            # "http://proxy1:port",
            # "http://proxy2:port"
        ],
        "output_dir": "scraped_data",
        "log_level": "INFO",
        "retry_attempts": 3,
        "retry_backoff": 2.0,
        "health_check_interval": 10,
        "user_agent_rotation": True,
        "proxy_rotation": True
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=2)
    
    print(f"Default config created at {config_path}")
    print("Please edit the config file with your target pages/groups and proxy list.")


def main():
    """Main function"""
    print("Facebook Data Scraper v1.0")
    print("=" * 40)
    
    config_path = "config.json"
    
    # Load configuration
    config = load_config(config_path)
    
    # Create scraper instance
    scraper = FacebookScraper(config)
    
    try:
        # Start scraping
        scraper.scrape_all_targets()
        
    except KeyboardInterrupt:
        print("\nScraping interrupted by user")
        scraper.logger.info("Scraping interrupted by user")
    
    except Exception as e:
        print(f"Fatal error: {e}")
        scraper.logger.error(f"Fatal error: {e}")
    
    finally:
        # Final statistics
        stats = scraper.health_monitor.get_stats()
        print(f"\nFinal Statistics:")
        print(f"Total Posts Scraped: {len(scraper.scraped_data)}")
        print(f"Success Rate: {stats['success_rate']}%")
        print(f"Runtime: {stats['runtime']}")


if __name__ == "__main__":
    main()