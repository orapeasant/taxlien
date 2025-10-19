import asyncio, os
from bas_extract.playwright_scraper import main

#TARGETS = ["albion","altona","amenia","amherst","amityville","cliftonpark"]
TARGETS = ["cliftonpark"]

if __name__ == "__main__":
    rows = asyncio.run(main(TARGETS))
    print(f"Extracted {len(rows)} rows")
