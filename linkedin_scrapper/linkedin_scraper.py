#!/usr/bin/env python3
"""
LinkedIn Data Scraper
A comprehensive LinkedIn scraper with security features and rate limiting.
Uses the unofficial linkedin-api library.

Author: AI Assistant
Date: 2025
"""

import os
import sys
import time
import json
import random
import logging
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re
from dotenv import load_dotenv  # Add this import

try:
    from linkedin_api import Linkedin
except ImportError:
    print("Error: linkedin_api not installed. Please run: pip install linkedin-api")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('linkedin_scraper.log'),
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('linkedin_scraper_terminal_output.txt')  # New handler for terminal output
    ]
)
logger = logging.getLogger(__name__)

# --- Tee class for duplicating stdout ---
class Tee(object):
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

class LinkedInScraper:
    """
    Advanced LinkedIn scraper with security features and rate limiting.
    """
    
    def __init__(self, config_file: str = "config.json"):
        """
        Initialize the LinkedIn scraper.
        
        Args:
            config_file (str): Path to configuration file
        """
        load_dotenv()  # Load environment variables from .env
        self.config = self._load_config(config_file)
        self.session_file = "linkedin_session.pkl"
        self.linkedin = None
        self.request_count = 0
        self.last_request_time = 0
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:120.0) Gecko/20100101 Firefox/120.0'
        ]
        self.current_user_agent = random.choice(self.user_agents)
        
        # Initialize session with retry strategy
        self.session = self._create_session()
        
        # Rate limiting configuration
        self.min_delay = self.config.get('min_delay', 5)
        self.max_delay = self.config.get('max_delay', 10)
        self.max_requests_per_hour = self.config.get('max_requests_per_hour', 50)
        
        logger.info("LinkedIn Scraper initialized successfully")
    
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file {config_file} not found")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            return {}
    
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy and proxy support."""
        session = requests.Session()
        
        # Retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Set headers
        session.headers.update({
            'User-Agent': self.current_user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
        # Configure proxy if provided
        if self.config.get('proxy'):
            proxy_config = {
                'http': self.config['proxy'],
                'https': self.config['proxy']
            }
            session.proxies.update(proxy_config)
            logger.info(f"Using proxy: {self.config['proxy']}")
        
        return session
    
    def _rate_limit(self):
        """Implement rate limiting between requests."""
        current_time = time.time()
        
        # Check if we've exceeded hourly limit
        if hasattr(self, 'request_times'):
            self.request_times = [t for t in self.request_times if current_time - t < 3600]
            if len(self.request_times) >= self.max_requests_per_hour:
                sleep_time = 3600 - (current_time - self.request_times[0])
                logger.warning(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        else:
            self.request_times = []
        
        # Random delay between min and max
        delay = random.uniform(self.min_delay, self.max_delay)
        
        # Ensure minimum time between requests
        if self.last_request_time:
            time_since_last = current_time - self.last_request_time
            if time_since_last < delay:
                sleep_time = delay - time_since_last
                logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        self.last_request_time = time.time()
        self.request_count += 1
        self.request_times.append(self.last_request_time)
        
        # Rotate user agent occasionally
        if self.request_count % 10 == 0:
            self.current_user_agent = random.choice(self.user_agents)
            logger.info("Rotated user agent")
    
    def _save_session(self):
        """Save LinkedIn session to file for reuse."""
        try:
            if self.linkedin:
                with open(self.session_file, 'wb') as f:
                    pickle.dump(self.linkedin.client.session.cookies, f)
                logger.info("Session saved successfully")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
    
    def _load_session(self) -> bool:
        """Load LinkedIn session from file."""
        try:
            if os.path.exists(self.session_file):
                with open(self.session_file, 'rb') as f:
                    cookies = pickle.load(f)
                
                # Create LinkedIn instance and set cookies
                self.linkedin = Linkedin('', '', refresh_cookies=True)
                self.linkedin.client.session.cookies.update(cookies)
                
                # Test if session is still valid
                try:
                    self.linkedin.get_profile('linkedin')  # Test with LinkedIn's own profile
                    logger.info("Loaded existing session successfully")
                    return True
                except Exception as e:
                    logger.warning(f"Existing session invalid: {e}")
                    os.remove(self.session_file)
                    return False
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            return False
    
    def authenticate(self, username: str = None, password: str = None) -> bool:
        """
        Authenticate with LinkedIn.
        
        Args:
            username (str): LinkedIn username/email
            password (str): LinkedIn password
            
        Returns:
            bool: True if authentication successful
        """
        # Try to load existing session first
        if self._load_session():
            return True
        
        # Use credentials from environment variables if not provided
        if not username:
            username = os.getenv('LINKEDIN_USERNAME')
        if not password:
            password = os.getenv('LINKEDIN_PASSWORD')
        
        if not username or not password:
            logger.error("Username and password required for authentication. Please set LINKEDIN_USERNAME and LINKEDIN_PASSWORD in your .env file.")
            return False
        
        try:
            logger.info("Authenticating with LinkedIn...")
            self.linkedin = Linkedin(username, password)
            self._save_session()
            logger.info("Authentication successful")
            return True
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False
    
    def get_profile(self, profile_id: str) -> Optional[Dict]:
        """
        Get a LinkedIn profile by ID or public identifier.
        
        Args:
            profile_id (str): LinkedIn profile ID or public identifier
            
        Returns:
            Optional[Dict]: Profile data or None if failed
        """
        if not self.linkedin:
            logger.error("Not authenticated. Please authenticate first.")
            return None
        
        try:
            self._rate_limit()
            logger.info(f"Fetching profile: {profile_id}")
            
            profile = self.linkedin.get_profile(profile_id)
            
            if profile:
                logger.info(f"Successfully fetched profile: {profile.get('firstName', '')} {profile.get('lastName', '')}")
                return profile
            else:
                logger.warning(f"No profile found for: {profile_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch profile {profile_id}: {e}")
            return None
    
    def get_profile_connections(self, profile_id: str) -> Optional[List]:
        """
        Get connections for a LinkedIn profile.
        
        Args:
            profile_id (str): LinkedIn profile ID
            
        Returns:
            Optional[List]: List of connections or None if failed
        """
        if not self.linkedin:
            logger.error("Not authenticated. Please authenticate first.")
            return None
        
        try:
            self._rate_limit()
            logger.info(f"Fetching connections for: {profile_id}")
            
            connections = self.linkedin.get_profile_connections(profile_id)
            
            if connections:
                logger.info(f"Found {len(connections)} connections for {profile_id}")
                return connections
            else:
                logger.warning(f"No connections found for: {profile_id}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to fetch connections for {profile_id}: {e}")
            return None
    
    def search_people(self, keywords: str, limit: int = 10) -> Optional[List]:
        """
        Search for people on LinkedIn.
        
        Args:
            keywords (str): Search keywords
            limit (int): Maximum number of results
            
        Returns:
            Optional[List]: List of search results or None if failed
        """
        if not self.linkedin:
            logger.error("Not authenticated. Please authenticate first.")
            return None
        
        try:
            self._rate_limit()
            logger.info(f"Searching people with keywords: {keywords}")
            results = self.linkedin.search_people(keywords, limit=limit)
            logger.debug(f"Raw search_people results for '{keywords}': {results}")
            if results:
                logger.info(f"Found {len(results)} people for search: {keywords}")
                return results
            else:
                logger.warning(f"No people found for search_people: {keywords}. Trying lower-level search().")
                # Try the lower-level search method
                try:
                    alt_results = self.linkedin.search({"keywords": keywords}, limit=limit)
                    logger.debug(f"Raw search() results for '{keywords}': {alt_results}")
                    if alt_results:
                        logger.info(f"Found {len(alt_results)} people for search() with: {keywords}")
                        return alt_results
                    else:
                        logger.warning(f"No people found for search() with: {keywords}")
                        return []
                except Exception as e2:
                    logger.error(f"Lower-level search() failed for {keywords}: {e2}")
                    return []
        except Exception as e:
            logger.error(f"Failed to search people with keywords {keywords}: {e}")
            return None
    
    def search_companies(self, keywords: str, limit: int = 10) -> Optional[List]:
        """
        Search for companies on LinkedIn.
        
        Args:
            keywords (str): Search keywords
            limit (int): Maximum number of results
            
        Returns:
            Optional[List]: List of search results or None if failed
        """
        if not self.linkedin:
            logger.error("Not authenticated. Please authenticate first.")
            return None
        
        try:
            self._rate_limit()
            logger.info(f"Searching companies with keywords: {keywords}")
            
            results = self.linkedin.search_companies(keywords, limit=limit)
            
            if results:
                logger.info(f"Found {len(results)} companies for search: {keywords}")
                return results
            else:
                logger.warning(f"No companies found for search: {keywords}")
                return []
                
        except Exception as e:
            logger.error(f"Failed to search companies with keywords {keywords}: {e}")
            return None
    
    def get_company(self, company_id: str) -> Optional[Dict]:
        """
        Get company information by ID.
        
        Args:
            company_id (str): LinkedIn company ID
            
        Returns:
            Optional[Dict]: Company data or None if failed
        """
        if not self.linkedin:
            logger.error("Not authenticated. Please authenticate first.")
            return None
        
        try:
            self._rate_limit()
            logger.info(f"Fetching company: {company_id}")
            
            company = self.linkedin.get_company(company_id)
            
            if company:
                logger.info(f"Successfully fetched company: {company.get('name', '')}")
                return company
            else:
                logger.warning(f"No company found for: {company_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to fetch company {company_id}: {e}")
            return None
    
    def scrape_profiles_from_search(self, keywords: str, max_profiles: int = 50) -> List[Dict]:
        """
        Scrape multiple profiles from search results.
        
        Args:
            keywords (str): Search keywords
            max_profiles (int): Maximum number of profiles to scrape
            
        Returns:
            List[Dict]: List of profile data
        """
        profiles = []
        
        # Search for people
        search_results = self.search_people(keywords, limit=max_profiles)
        if not search_results:
            return profiles
        
        count = 0
        for result in search_results:
            profile_id = None
            if isinstance(result, dict):
                # Try to get public_id (for search_people)
                profile_id = result.get('public_id')
                # If not found, try to extract from entityUrn (for search())
                if not profile_id:
                    entity_urn = result.get('entityUrn')
                    # Only process if it's a profile entity
                    if entity_urn and entity_urn.startswith('urn:li:fsd_profile:'):
                        # Extract the profile id after the last colon
                        profile_id = entity_urn.split(':')[-1]
            # Only proceed if we have a valid, clean profile_id (should look like ACoAA... etc.)
            if profile_id and profile_id.startswith('AC') and ',' not in profile_id and ')' not in profile_id:
                profile = self.get_profile(profile_id)
                if profile:
                    profiles.append(profile)
                    profile['scraped_at'] = datetime.now().isoformat()
                    profile['search_keywords'] = keywords
                    count += 1
                    if count >= max_profiles:
                        break
            else:
                logger.debug(f"Skipping non-profile or malformed result: {result}")
                continue
        
        logger.info(f"Scraped {len(profiles)} profiles from search: {keywords}")
        return profiles
    
    def save_data(self, data: Any, filename: str):
        """
        Save scraped data to JSON file.
        
        Args:
            data (Any): Data to save
            filename (str): Output filename
        """
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Data saved to {filename}")
        except Exception as e:
            logger.error(f"Failed to save data to {filename}: {e}")
    
    def health_check(self) -> Dict:
        """
        Check scraper health and status.
        
        Returns:
            Dict: Health status information
        """
        status = {
            'authenticated': self.linkedin is not None,
            'total_requests': self.request_count,
            'last_request_time': self.last_request_time,
            'current_user_agent': self.current_user_agent,
            'session_file_exists': os.path.exists(self.session_file),
            'timestamp': datetime.now().isoformat()
        }
        
        if hasattr(self, 'request_times'):
            status['requests_last_hour'] = len(self.request_times)
        
        return status


def main():
    """
    Main function to demonstrate scraper usage.
    """
    # Duplicate stdout to both terminal and txt file
    tee_file = open('linkedin_scraper_terminal_output.txt', 'a', encoding='utf-8')
    sys.stdout = Tee(sys.__stdout__, tee_file)
    # Initialize scraper
    scraper = LinkedInScraper()
    
    # Set logger to debug for troubleshooting
    logger.setLevel(logging.DEBUG)
    for handler in logger.handlers:
        handler.setLevel(logging.DEBUG)
    
    # Authenticate
    if not scraper.authenticate():
        logger.error("Authentication failed. Please check your credentials.")
        return
    
    # Example usage
    try:
        
        # Get a specific profile
        profile = scraper.get_profile('williamhgates')
        if profile:
            scraper.save_data(profile, 'profile_example.json')
        
        # Search for people
        search_results = scraper.search_people('python developer', limit=5)
        if search_results:
            scraper.save_data(search_results, 'search_results.json')
        else:
            logger.warning("No results for 'python developer'. Trying fallback search for 'Bill Gates'.")
            fallback_results = scraper.search_people('Bill Gates', limit=2)
            if fallback_results:
                scraper.save_data(fallback_results, 'search_results_fallback.json')
            else:
                logger.error("Fallback search also returned no results.")
        '''
        # Scrape multiple profiles from search
        profiles = scraper.scrape_profiles_from_search('data scientist', max_profiles=6)
        if profiles:
            scraper.save_data(profiles, 'scraped_profiles.json')
        else:
            logger.warning("No profiles scraped for 'data scientist'. Trying fallback scrape for 'CEO'.")
            fallback_profiles = scraper.scrape_profiles_from_search('CEO', max_profiles=2)
            if fallback_profiles:
                scraper.save_data(fallback_profiles, 'scraped_profiles_fallback.json')
            else:
                logger.error("Fallback scrape also returned no profiles.")
        ''' 
        # Health check
        health = scraper.health_check()
        logger.info(f"Scraper health: {health}")
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    
    logger.info("Scraping completed")


if __name__ == "__main__":
    main()