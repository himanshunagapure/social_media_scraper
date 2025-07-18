# Social Media Scraping Methods & Limitations (2025)

This document summarizes the methods, libraries, and official APIs used for scraping data from major social media platforms, along with their rate limits, restrictions, and compliance with Terms of Service (TOS) as of 2025.

---

## Reddit

### API: [PRAW](https://praw.readthedocs.io/)
- **Authenticated (OAuth) requests:** Up to **100 queries per minute (QPM)** per OAuth client ID
- **Unauthenticated requests:** Limited to **10 QPM**
- **PRAW** auto-throttles if Reddit returns a rate-limit error (waits up to `ratelimit_seconds`, default 300s)
- **What counts as a “query”?**
  - Each API call (fetching post, comment, etc.) counts as one query

---

## YouTube

### API: [YouTube Data API](https://developers.google.com/youtube/v3)
- **Daily quota per Google Cloud project:** 10,000 units
- **Quota cost per request:**
  - Simple read (video details, comments): 1 unit each
  - Comment insert/delete/reply: ≈50 units
  - Search requests: typically 100 units each
- **No explicit rate-per-minute limit**; quota is enforced per day (resets at 00:00 PT)

---

## Twitter/X

### Can You Fetch Without Login?
- **No reliable way in 2025:**
  - Twitter/X blocks guest search and data endpoints
  - Playwright without login shows only limited or no content
  - Only ~40 tweets viewable as incognito user
  - All search endpoints require login

### 1. Browser Automation (Playwright)
- **Login required** for most data
- **Rate Limit:** ~300–500 tweets/session
- **Blocking:**
  - Blocked after ~200–400 tweets/session
  - CAPTCHA triggers after repeated/fast scraping
  - Headless browsers often detected (need stealth/human-like delays)
- **No official quota or API stability**

### 2. [twscrape](https://github.com/vladkens/twscrape) (Used)
- **Can scrape:** search results, user profiles, tweets, etc.
- **Rate Limit:** ~100–200 requests/hour/account
- **Limitations:**
  - May break if Twitter changes GraphQL APIs
  - Still against Twitter’s TOS
  - Needs manual login occasionally to refresh tokens
- **Account Requirements:**
  - Valid Twitter username and password
  - Email address (required)
  - Phone number (recommended)

### 3. Official Twitter API v2
- **Free Tier:**
  - Read Access: ❌ No public read endpoints (GET)
  - Write Access: 1,500 tweets/month per app
- **Basic Tier (Paid):**
  - Cost: $100–$200/month
  - Read Quota: 10,000 read requests/month per app

---

## Instagram

### Unofficial Methods
- **Non-public APIs or illicit means** violate Instagram’s TOS
- **Disguising scrapers** as ordinary users is unauthorized

### [instagrapi](https://github.com/adw0rd/instagrapi) (Used)
- **Fetches:** public data (user info, bio, follower/following counts, hashtags, locations, posts, comments, like lists)
- **Login:**
  - Can fetch some data anonymously (very limited)
  - Most features require login
- **Rate Limits & Throttling:**
  1. 429 errors after ~20–80 user/media fetches per run
  2. Sessions on VPS/datacenter IPs often fail login (flagged by Instagram)
- **Issues:**
  1. API call may work, but media items rejected by library’s strict validation
  2. Violates TOS: warnings from Instagram
  3. Scraping at scale likely triggers bot detection
- **Best for:** Small research/testing, not heavy scraping

### Official Instagram Graph API
- **What it provides:**
  - Access only to your own Business/Creator account’s data (posts, comments, insights)
  - Cannot fetch other users’ public data
  - Compliant with Instagram’s TOS
- **Free-tier limitations:**
  - Must convert to Business/Creator account
  - Hard rate limits (~200 calls/hour per user)
  - Requires app review and Facebook Developer account

### Browser Automation (Selenium, Playwright)
- **Controls a real browser** to interact with Instagram’s public web pages
- **Full page control:** scrolling, clicking, lazy-load
- **Limitations:**
  - Performance-heavy (slow, high CPU/RAM)
  - Highly rate-limited (captchas, login walls, IP bans)
  - Maintenance-fragile (page changes break scripts)
  - Violates TOS

---

## Facebook

- **Extremely difficult to access public data programmatically in 2025**
- **Strict anti-scraping measures**
- **Unauthorized scraping forbidden**
- **Scraper detection:**
  - Account can be permanently banned
  - Public posts often return blank/blocked pages without login
  - Layout changes break scrapers
  - CAPTCHAs and permission errors common
  - Trusted tools may stop working after backend changes

### [facebook-scraper](https://github.com/kevinzg/facebook-scraper)
- **Scrapes:** public data from Facebook pages (public posts, page metadata, visible comments, reactions)
- **Limitations:**
  - Works only on public pages
  - May fail if Facebook changes layout
  - No support for private posts/groups without login
  - Designed for research/small-scale use

### Facebook Graph API (Official Method)
- **What it provides:**
  - Fetch data like posts, comments, photos from profiles, pages, or groups
- **Limitations & Issues:**
  - Requires permission and access token
  - Each request is tracked and rate-limited
  - Cannot access public group members, competitor pages, or user posts unless admin/consent
  - Cannot extract large volumes of public-facing content
  - Linked to app’s permissions
  - Anything beyond these limits violates Facebook’s TOS
- **Application Process:**
  - Anyone can apply with Developer account and proper app setup
  - Approval not guaranteed (must justify use case and meet permissions)
  - Typical review time: 3 days to 2 months (sometimes as fast as 24–48 hours)

---

## LinkedIn

### linkedin-api (Unofficial)
- **Login Required:** Yes — You need to log in with a valid LinkedIn account (email + password)
- **Data You Can Fetch:**
  - Profiles (public & private fields)
  - Contact info (if available)
  - Search results (Classic, Sales Navigator, Recruiter)
  - Messages, invitations, posts, replies
- **Current Status:**
  - Get a specific profile
  - Search for people
  - Not able to scrape multiple profiles from search
- **Cons & Limitations:**
  - Unofficial — violates LinkedIn Terms of Service
  - LinkedIn often changes internal API endpoints, so features can break often
  - High risk of account suspension, CAPTCHA, or cookie expiration
  - Requires careful handling of cookies, headers, rate-limiting

### linkedin-scraper (Unofficial)
- Similar to linkedin-api, but uses Selenium (browser automation)

### LinkedIn Developer API (Official)
- **Public Access:** No longer available. Businesses must join the LinkedIn Partner Program to gain access.
- **Marketing Developer Platform:** For integrating marketing-related functionalities through Advertising APIs.
- **Fetching data about other users or companies:** Requires partner access, which is hard to get and limited to business/trusted apps.
- **Partner Program Tracks:**
  - Marketing Developer Program
  - Sales Navigator Solutions
  - Talent Solutions Partnership
  - LinkedIn Learning Partner Program
- **Partner Program (Free Tier) Restrictions:**
  - 200 profile requests per 24 hours
  - 1,000 search requests per 24 hours
  - Limited number of shared content requests
- **Paid Tiers:**
  - Professional Tier: Unlimited search & profile scraping, higher rate limits for sharing content
  - Business Tier: More API endpoints and access to more granular data
  - Enterprise Tier: Widest range of LinkedIn API features and data access

---

## Summary Table

| Platform   | Official API         | Unofficial Methods         | Rate Limits / Quotas                                              | TOS Compliance      |
|------------|---------------------|---------------------------|-------------------------------------------------------------------|---------------------|
| Reddit     | PRAW                | N/A                       | 100 QPM (auth), 10 QPM (unauth)                                   | Yes                |
| YouTube    | Data API            | N/A                       | 10,000 units/day                                                  | Yes                |
| Twitter/X  | v2 API              | Playwright, twscrape       | 10,000 reads/month (paid), ~100–500 req/hr (unofficial)           | No (unofficial)     |
| Instagram  | Graph API           | instagrapi, browser        | ~200 calls/hr (official), ~20–80 fetches/run (unofficial)         | No (unofficial)     |
| Facebook   | Graph API           | facebook-scraper, browser  | Strict, permissioned, tracked                                     | No (unofficial)     |
| LinkedIn   | Partner Program API | linkedin-api, selenium     | 200 profiles/24h (free), higher with paid; unofficial: fragile    | No (unofficial)     |

---

**Note:**
- Unofficial methods often violate platform TOS and may result in bans, CAPTCHAs, or legal issues.
- Official APIs are limited in scope and require proper permissions and review.
- Always check the latest documentation and TOS before scraping any platform. 