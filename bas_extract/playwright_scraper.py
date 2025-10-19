import asyncio, os, re
from datetime import datetime
from playwright.async_api import async_playwright
from .utils import sleep_ms
from .parsers import parse_table_rows
from .storage import persist_rows, save_snapshot
from .municipalities import DEFAULT_COLLECTIONS_PER_SLUG

UA_EXTRA = os.getenv("BAS_CONTACT_EMAIL","")

async def fetch_bill_details(page, bill_url: str):
    """Fetch detailed bill information from the bill detail page"""
    await page.goto(bill_url, wait_until="domcontentloaded")
    #await sleep_ms(800)
    print("sleep 1 500 ms")
    await sleep_ms(500)

    # Extract data from the first table where Type column shows unpaid status
    bill_details = {}

    # Look for the first table with tax details
    tables = page.locator("table")
    if await tables.count() > 0:
        first_table = tables.first
        rows = await first_table.locator("tr").all()

        for row in rows:
            cells = await row.locator("td, th").all()
            if len(cells) >= 2:
                header = (await cells[0].inner_text()).strip()
                value = (await cells[1].inner_text()).strip()

                # Map common fields
                if "type" in header.lower():
                    bill_details["type"] = value
                elif "amount" in header.lower():
                    bill_details["amount"] = value
                elif "due date" in header.lower() or "penalty date" in header.lower():
                    bill_details["due_date"] = value
                elif "balance" in header.lower():
                    bill_details["balance"] = value
                elif "status" in header.lower():
                    bill_details["status"] = value

    return bill_details

async def extract_bill_data_from_current_page(page, municipality_slug: str, collection_label: str, search_address: str, ts: str):
    """Extract bill data from the current bill detail page"""
    record = {
        "municipality_slug": municipality_slug,
        "collection": collection_label,
        "search_address": search_address,
        "extracted_at": ts,
        "source_url": page.url
    }

    # Extract owner information from the property information table
    owner_name_element = page.locator("td.tablecontent").filter(has_text=re.compile(r"[A-Za-z]+ [A-Za-z]+")).first
    if await owner_name_element.count() > 0:
        record["owner_name"] = (await owner_name_element.inner_text()).strip()

    # Extract property address
    address_element = page.locator("td.tablecontent").filter(has_text=re.compile(r"\d+.*\w+.*St|Rd|Ave|Dr|Ln|Way|Blvd")).first
    if await address_element.count() > 0:
        address_text = (await address_element.inner_text()).strip()
        # Clean up the address (remove <br> tags)
        record["property_address"] = address_text.replace('<br>', ' ').replace('\n', ' ')

    # Extract tax bill information from BillUserControl1_gdvTaxBill table
    tax_bill_table = page.locator("#BillUserControl1_gdvTaxBill")
    if await tax_bill_table.count() > 0:
        rows = await tax_bill_table.locator("tr").all()
        for row in rows:
            cells = await row.locator("td").all()
            if len(cells) >= 4:
                bill_id = (await cells[0].inner_text()).strip()
                swis = (await cells[1].inner_text()).strip()
                tax_map = (await cells[2].inner_text()).strip()
                status = (await cells[3].inner_text()).strip()

                record["bill_id"] = bill_id
                record["swis"] = swis
                record["parcel_id"] = tax_map
                record["bill_status"] = status

    # Extract transaction information to check payment type
    transaction_table = page.locator("#BillUserControl1_gdvTransaction")
    is_unpaid = False
    if await transaction_table.count() > 0:
        # Look for the Type column in transaction data
        rows = await transaction_table.locator("tr").all()
        for row in rows:
            cells = await row.locator("td").all()
            if len(cells) >= 8:  # Based on the HTML structure
                payment_type = (await cells[7].inner_text()).strip().lower()
                record["payment_type"] = payment_type

                # Check if this indicates unpaid status
                if "unpaid" in payment_type or "due" in payment_type or "outstanding" in payment_type:
                    is_unpaid = True
                elif "full payment" in payment_type or "payment" in payment_type:
                    is_unpaid = False

    # Extract total tax amount
    total_tax_element = page.locator("text=Total Taxes:").locator("xpath=following-sibling::*").first
    if await total_tax_element.count() == 0:
        # Try alternative selector
        total_tax_element = page.locator("td").filter(has_text=re.compile(r"Total Taxes:\s*\$[\d,]+\.\d{2}")).first
    if await total_tax_element.count() > 0:
        total_text = (await total_tax_element.inner_text()).strip()
        # Extract dollar amount
        amount_match = re.search(r'\$[\d,]+\.\d{2}', total_text)
        if amount_match:
            record["total_taxes"] = amount_match.group()

    # Check "Total Tax Due" which should indicate if there's an outstanding balance
    total_due_element = page.locator("text=Total Tax Due (minus penalties & interest)").locator("xpath=following-sibling::*").first
    if await total_due_element.count() > 0:
        due_text = (await total_due_element.inner_text()).strip()
        record["amount_due"] = due_text
        # If amount due is greater than $0.00, it's unpaid
        if due_text and "$0.00" not in due_text and "$" in due_text:
            is_unpaid = True

    record["is_unpaid"] = is_unpaid
    return record, is_unpaid

async def process_pagination(page, view_bill_links_selector, municipality_slug: str, collection_label: str, search_term: str, ts: str, all_records: list):
    """Process all pages of search results with pagination support"""
    current_page = 1
    max_pages = 10  # Reasonable limit to prevent infinite loops

    while current_page <= max_pages:
        print(f"Processing page {current_page} for search term '{search_term}'")

        # Look for "view bill" links on current page
        view_bill_links = page.locator(view_bill_links_selector)
        link_count = await view_bill_links.count()

        if link_count > 0:
            print(f"Found {link_count} 'view bill' links on page {current_page}")

            # Process each view bill link on this page
            for i in range(link_count):
                try:
                    # Get the href of the current link
                    link = view_bill_links.nth(i)
                    href = await link.get_attribute("href")

                    if href:
                        # Make the URL absolute if it's relative
                        if href.startswith("/"):
                            from urllib.parse import urljoin
                            bill_url = urljoin(page.url, href)
                        elif not href.startswith("http"):
                            bill_url = f"{page.url.rstrip('/')}/{href}"
                        else:
                            bill_url = href

                        print(f"Processing bill {i+1}/{link_count} on page {current_page}: {bill_url}")

                        # Navigate to the bill detail page
                        await page.goto(bill_url, wait_until="domcontentloaded")
                        #await sleep_ms(800)
                        print("sleep 2 500 ms")
                        await sleep_ms(500)

                        # Extract data from this bill detail page
                        record, is_unpaid = await extract_bill_data_from_current_page(
                            page, municipality_slug, collection_label, str(search_term), ts
                        )

                        # Add ALL records (both paid and unpaid) to the dataset
                        all_records.append(record)

                        if is_unpaid:
                            print(f"Found UNPAID record: {record.get('owner_name', 'Unknown')} - Amount due: {record.get('amount_due', 'Unknown')}")
                        else:
                            print(f"Found PAID record: {record.get('owner_name', 'Unknown')} - Status: {record.get('payment_type', 'Paid')}")

                        # Navigate back to search results page for next link
                        await page.go_back()
                        #await sleep_ms(800)
                        print("sleep 3 500 ms")
                        await sleep_ms(500)


                        # Re-locate the view bill links after going back
                        view_bill_links = page.locator(view_bill_links_selector)

                except Exception as e:
                    print(f"[WARN] Error processing bill link {i+1} on page {current_page}: {e}")
                    continue

        # Look for "Next" or pagination links
        next_page_found = False
        next_selectors = [
            "a:has-text('Next')",
            "a:has-text('>')",
            f"a:has-text('{current_page + 1}')",
            "input[value='Next']",
            "button:has-text('Next')"
        ]

        for selector in next_selectors:
            next_link = page.locator(selector)
            if await next_link.count() > 0:
                try:
                    await next_link.first.click()
                    await page.wait_for_load_state("networkidle")
                    print("sleep 4.  800 ms")
                    await sleep_ms(800)
                    next_page_found = True
                    current_page += 1
                    break
                except Exception as e:
                    print(f"[WARN] Error clicking next page with selector '{selector}': {e}")
                    continue

        if not next_page_found:
            print(f"No more pages found after page {current_page}")
            break

    return len(all_records)

async def fetch_collection(page, base_url:str, collection_label:str, municipality_slug:str, do_snapshot:bool):
    await page.goto(base_url, wait_until="domcontentloaded")
    print("sleep 5. 500 ms")
    await sleep_ms(500)

    # Select the collection if there's a dropdown
    select = page.locator("select").first
    if await select.count() > 0:
        try:
            await select.select_option(label=collection_label)
        except:
            await page.locator("option", has_text=collection_label).click()
    else:
        # Try to click on the collection label if it's not a dropdown
        collection_link = page.get_by_text(collection_label, exact=True)
        if await collection_link.count() > 0:
            await collection_link.click()
    print("sleep 6.12 600 ms")
    await sleep_ms(600)

    # Find the address input field - try multiple selectors
    address_input = page.locator("input[placeholder*='Address']")
    if await address_input.count() == 0:
        address_input = page.get_by_label(re.compile("Address", re.I))
    if await address_input.count() == 0:
        address_input = page.locator("input[name*='address']")
    if await address_input.count() == 0:
        address_input = page.locator("input[id*='address']")
    if await address_input.count() == 0:
        # Try to find any text input that might be for address
        address_input = page.locator("input[type='text']").first

    print(f"Found {await address_input.count()} address input field(s)")

    # Find the search button
    search_btn = page.get_by_role("button", name=re.compile("search", re.I))
    if await search_btn.count() == 0:
        search_btn = page.locator("input[type=submit]").filter(has_text=re.compile("search", re.I))
    if await search_btn.count() == 0:
        search_btn = page.locator("button").filter(has_text=re.compile("search", re.I))

    all_records = []
    ts = datetime.utcnow().isoformat()

    # Generate comprehensive search terms for maximum coverage
    search_terms = []

    # Add numeric addresses: 1-999
    search_terms.extend([str(i) for i in range(1, 1000)])

    # Add alphabetic addresses: A-Z
    search_terms.extend([chr(i) for i in range(ord('A'), ord('Z') + 1)])

    print(f"Starting comprehensive search with {len(search_terms)} search terms for {municipality_slug} {collection_label}")

    # Search through all terms with progress tracking
    total_terms = len(search_terms)
    processed_terms = 0

    for address_num in search_terms:
        try:
            print(f"Searching {municipality_slug} {collection_label} with address: {address_num}")

            # Clear and fill the address field
            if await address_input.count() > 0:
                await address_input.first.clear()
                await address_input.first.fill(str(address_num))
                print("sleep 7. 500 ms")
                await sleep_ms(100)

                # Click search button
                if await search_btn.count() > 0:
                    await search_btn.first.click()
                    await page.wait_for_load_state("networkidle")
                    print("sleep 8 500 ms")
                    await sleep_ms(500)
                else:
                    # Try pressing Enter if no search button
                    await address_input.first.press("Enter")
                    await page.wait_for_load_state("networkidle")
                    print("sleep 9 500 ms")
                    await sleep_ms(500)

                # Check if we're on a bill detail page OR a search results page
                page_title = await page.title()

                if "View Bill" in page_title:
                    # We're on a bill detail page - extract data from this single bill
                    record, is_unpaid = await extract_bill_data_from_current_page(
                        page, municipality_slug, collection_label, str(address_num), ts
                    )

                    # Add ALL records (both paid and unpaid) to the dataset
                    all_records.append(record)

                    if is_unpaid:
                        print(f"Found UNPAID record for {municipality_slug}: {record.get('owner_name', 'Unknown')} - Amount due: {record.get('amount_due', 'Unknown')}")
                    else:
                        print(f"Found PAID record for {municipality_slug}: {record.get('owner_name', 'Unknown')} - Status: {record.get('payment_type', 'Paid')}")

                else:
                    # We might be on a search results page with multiple properties
                    # Save a snapshot for debugging if this is the first search
                    if address_num == 1 and do_snapshot:
                        snap_path = await save_snapshot(page)
                        print(f"Saved snapshot of search results to: {snap_path}")

                    # Look for "view bill" links or property list on this page
                    view_bill_links = page.locator("a").filter(has_text=re.compile("view bill", re.I))
                    link_count = await view_bill_links.count()

                    if link_count > 0:
                        print(f"Found {link_count} 'view bill' links for address {address_num}")

                        # Process each view bill link
                        for i in range(link_count):
                            try:
                                # Get the href of the current link
                                link = view_bill_links.nth(i)
                                href = await link.get_attribute("href")

                                if href:
                                    # Make the URL absolute if it's relative
                                    if href.startswith("/"):
                                        from urllib.parse import urljoin
                                        bill_url = urljoin(base_url, href)
                                    elif not href.startswith("http"):
                                        bill_url = f"{base_url.rstrip('/')}/{href}"
                                    else:
                                        bill_url = href

                                    print(f"Processing bill {i+1}/{link_count}: {bill_url}")

                                    # Navigate to the bill detail page
                                    await page.goto(bill_url, wait_until="domcontentloaded")
                                    print("sleep 10. 200 ms")
                                    await sleep_ms(200)

                                    # Extract data from this bill detail page
                                    record, is_unpaid = await extract_bill_data_from_current_page(
                                        page, municipality_slug, collection_label, str(address_num), ts
                                    )

                                    # Add ALL records (both paid and unpaid) to the dataset
                                    all_records.append(record)

                                    if is_unpaid:
                                        print(f"Found UNPAID record for {municipality_slug}: {record.get('owner_name', 'Unknown')} - Amount due: {record.get('amount_due', 'Unknown')}")
                                    else:
                                        print(f"Found PAID record for {municipality_slug}: {record.get('owner_name', 'Unknown')} - Status: {record.get('payment_type', 'Paid')}")

                                    # Navigate back to search results page for next link
                                    await page.go_back()
                                    print("sleep 11. 200 ms")
                                    await sleep_ms(200)

                                    # Re-locate the view bill links after going back
                                    view_bill_links = page.locator("a").filter(has_text=re.compile("view bill", re.I))

                            except Exception as e:
                                print(f"[WARN] Error processing bill link {i+1} for address {address_num}: {e}")
                                continue

                    else:
                        print(f"No 'view bill' links found for address {address_num}")

                # Navigate back to the main search page for next address search
                await page.goto(base_url, wait_until="domcontentloaded")
                print("sleep 12 500 ms")
                await sleep_ms(500)

                # Re-select collection if needed
                select = page.locator("select").first
                if await select.count() > 0:
                    try:
                        await select.select_option(label=collection_label)
                    except:
                        pass

                # Re-locate address input and search button for next iteration
                address_input = page.locator("input[placeholder*='Address']")
                if await address_input.count() == 0:
                    address_input = page.get_by_label(re.compile("Address", re.I))
                if await address_input.count() == 0:
                    address_input = page.locator("input[name*='address']")
                if await address_input.count() == 0:
                    address_input = page.locator("input[type='text']").first

                search_btn = page.get_by_role("button", name=re.compile("search", re.I))
                if await search_btn.count() == 0:
                    search_btn = page.locator("input[type=submit]").filter(has_text=re.compile("search", re.I))
            #print("delay os.getenv('BAS_RATE_DELAY_MS') ms")
            await sleep_ms(int(os.getenv("BAS_RATE_DELAY_MS","1500")))

        except Exception as e:
            print(f"[WARN] Error searching address {address_num} in {municipality_slug}: {e}")
            continue

    return all_records

async def run_for_municipality(browser, muni, collections, do_snapshot):
    ctx = await browser.new_context(user_agent=f"Mozilla/5.0 BAS-ResearchBot (+{UA_EXTRA})")
    page = await ctx.new_page()
    all_rows = []
    for col in collections:
        try:
            rows = await fetch_collection(page, muni["url"], col, muni["slug"], do_snapshot)
            all_rows.extend(rows)
        except Exception as e:
            print(f"[WARN] {muni['slug']} {col}: {e}")
        print("delay getenv(BAS_RATE_DELAY_MS) ms")
        await sleep_ms(int(os.getenv("BAS_RATE_DELAY_MS","1500")))
    await ctx.close()
    return all_rows

async def main(target_slugs):
    from .municipalities import MUNICIPALITIES
    do_snapshot = os.getenv("BAS_SNAPSHOT_HTML","false").lower() == "true"
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        for muni in MUNICIPALITIES:
            if target_slugs and muni["slug"] not in target_slugs:
                continue
            cols = DEFAULT_COLLECTIONS_PER_SLUG.get(muni["slug"], [])
            rows = await run_for_municipality(browser, muni, cols, do_snapshot)
            if rows:
                results.extend(rows)
        await browser.close()

    # Save all results to a single Excel file
    if results:
        await persist_rows(results)

    return results
