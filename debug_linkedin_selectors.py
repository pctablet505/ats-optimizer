import asyncio
from src.automation.drivers.linkedin import LinkedInDriver
from src.automation.drivers.base import SearchConfig

async def inspect():
    driver = LinkedInDriver(headless=False, user_data_dir='data/browser_profiles/chrome_bot/linkedin')
    await driver._start_browser()
    await driver._ensure_logged_in()
    
    params = 'keywords=ML%20Engineer%20GenAI&location=Bengaluru&f_TPR=r604800'
    url = 'https://www.linkedin.com/jobs/search/?' + params
    
    await driver._page.goto(url, wait_until='domcontentloaded')
    await asyncio.sleep(5)
    
    # Get all job cards
    cards = await driver._page.query_selector_all('[data-job-id]')
    print(f'Found {len(cards)} cards')
    
    if len(cards) > 0:
        # Check first card
        card = cards[0]
        html = await card.inner_html()
        print('\n=== FIRST CARD HTML (truncated) ===')
        # Write to file
        with open('debug_card.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Wrote full HTML ({len(html)} chars) to debug_card.html")
        print(html[:3000])
    
    await driver._close_browser()

asyncio.run(inspect())
