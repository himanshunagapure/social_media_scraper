import asyncio
from twitter_scraper.twitter_scraper import TwitterScraper

async def main():
    # Initialize scraper
    scraper = TwitterScraper()
    
    # Add your Twitter account (replace with your actual details)
    cookies = "ct0=b07633d53ff2c5ed19fb96f06bc0bda3e3f94a306649c11efcd65a00a947aac76e4c88bd70b01db4b0e5966719529c94203c4403518796f8a20d014f6df414e6494e666506eb9b0384124310aa665cf8; auth_token=cce8b6a5da2deabf14823796bc6bf05743d0fdb1; personalization_id=v1_YVrwks4LK+PiTh2HXQdeCg=="  # Replace with actual cookies
    
    await scraper.add_account(
        username="zeref_first",
        password="Movies@first$123", 
        email="moviesfirst114@gmail.com",
        email_password="Movies@first$123",
        cookies=cookies
    )
    
    # Login accounts
    await scraper.login_accounts()
    
    # 1. Search for tweets
    print("Searching for tweets...")
    tweets = await scraper.search_tweets("python programming", limit=10)
    await scraper.save_to_json(tweets, "python_tweets.json")
    print(f"Found {len(tweets)} tweets")
    
    # 2. Get user information
    print("Getting user info...")
    user_info = await scraper.get_user_info("elonmusk")
    print(f"User: {user_info['display_name']} (@{user_info['username']})")
    print(f"Followers: {user_info['followers_count']}")
    
    # 3. Get user's tweets
    print("Getting user tweets...")
    user_tweets = await scraper.get_user_tweets(user_info['id'], limit=20)
    await scraper.save_to_json(user_tweets, "elon_tweets.json")
    
    # 4. Get followers
    print("Getting followers...")
    followers = await scraper.get_followers(user_info['id'], limit=100)
    await scraper.save_to_json(followers, "elon_followers.json")
    
    # Close scraper
    await scraper.close()
    print("Scraping completed!")

if __name__ == "__main__":
    asyncio.run(main())