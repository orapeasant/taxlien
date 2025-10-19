# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TaxLien is a Python application that scrapes tax lien data from municipal websites (specifically BAS Government websites) using Playwright for browser automation. The application uses an address-based search approach to systematically discover properties, extracts detailed tax bill information from individual property pages, and exports comprehensive payment status data to Excel files.

## Common Development Commands

### Running the Application

To run the scraper for all configured municipalities:
```bash
python run.py
```

To run with a custom configuration (requires environment setup):
```bash
# Copy the example environment file and modify as needed
cp .env.example .env
# Edit .env to add your configuration
# Then run the script
python run.py
```


## Environment Configuration

The following environment variables can be configured:

- `BAS_RATE_DELAY_MS`: Delay between requests in milliseconds (default: 1500)
- `BAS_CONTACT_EMAIL`: Contact email used in the user agent string
- `BAS_SNAPSHOT_HTML`: Whether to save HTML snapshots (true/false)

## Code Architecture

The codebase is organized into the following components:

### Core Components

- **run.py**: Entry point that defines target municipalities and runs the scraper
- **bas_extract/**: Main package containing the scraper implementation

### Key Modules

- **playwright_scraper.py**: Contains the main scraping logic using Playwright
  - `main()`: Main entry point that sets up the browser and processes municipalities
  - `run_for_municipality()`: Runs the scraper for a specific municipality
  - `fetch_collection()`: Performs address-based searches and extracts data from bill detail pages
  - `extract_bill_data_from_current_page()`: Extracts comprehensive tax and payment data from individual property bill pages

- **parsers.py**: Contains functions for parsing HTML content
  - `parse_table_rows()`: Extracts structured data from HTML tables and searches for "view bill" links

- **storage.py**: Handles data persistence
  - `persist_rows()`: Exports extracted data to Excel files
  - `save_snapshot()`: Saves HTML snapshots of pages

- **municipalities.py**: Contains configuration data for supported municipalities
  - `MUNICIPALITIES`: List of municipality definitions (name, slug, URL)
  - `DEFAULT_COLLECTIONS_PER_SLUG`: Maps municipalities to their tax collection types

### Data Flow

1. The entry point (run.py) calls `main()` with a list of target municipalities
2. For each municipality, the scraper:
   - Creates a new browser context with a custom user agent
   - Navigates to the municipal website and selects the appropriate tax collection
   - Performs systematic address-based searches (entering numbers 1-9 in the address field)
   - For each search, the system handles two possible scenarios:

     **Scenario A - Direct Bill Access:** When search returns a single property (page title contains "View Bill"):
     - Extracts data directly from the current bill detail page
     - Captures owner name, property address, tax amounts, and payment status

     **Scenario B - Multiple Properties:** When search returns a list of properties:
     - Identifies all "view bill" links on the search results page
     - For each "view bill" link:
       - Navigates to the linked bill detail page
       - Extracts comprehensive property and payment data from bill tables
       - Navigates back to search results for the next property

   - **Data Extraction from Bill Detail Pages:**
     - Owner information from property information tables
     - Tax bill details (bill ID, SWIS, parcel ID, status) from tax bill tables
     - Payment information from transaction tables (specifically the "Type" column)
     - Financial data (total taxes, amount due) from summary sections

   - Captures all records regardless of payment status (paid and unpaid)
   - Saves consolidated data to timestamped Excel files
   - Optionally saves HTML snapshots for debugging/archival purposes

### Data Storage

Scraped data is exported to Excel files in the data/exports directory with the naming pattern `bas_all_records_YYYYMMDDTHHMMSS.xlsx`. Each export file contains comprehensive tax data including:

**Key Data Fields:**
- **Payment Status**: `is_unpaid` (boolean), `payment_type` (full payment, paid, bank payment, etc.), `bill_status`
- **Property Information**: `owner_name`, `property_address`, `parcel_id`, `bill_id`, `swis`
- **Financial Data**: `amount_due`, `total_taxes`, `amount_paid`, `due_date`
- **Metadata**: `municipality_slug`, `collection`, `search_address`, `extracted_at`

**File Organization**: Columns are intelligently ordered with payment status and property identification fields first, followed by financial data and metadata.

### Scraping Methodology

**Address-Based Discovery**: The scraper uses a systematic approach to discover properties by searching address numbers 1-9 in each municipality's tax collection system.

**Dual Processing Modes**:
1. **Direct Bill Access**: When a search returns a single property, the scraper extracts data directly from the bill detail page
2. **Multi-Property Processing**: When a search returns multiple properties, the scraper follows each "view bill" link to extract individual property data

**Data Extraction Points**:
- Transaction tables to determine payment status via the "Type" column
- Property information tables for owner names and addresses
- Tax bill tables for parcel IDs and bill numbers
- Financial summary sections for tax amounts and balances

**Quality Assurance**: The system captures both paid and unpaid records to provide a complete dataset for analysis, with clear payment status indicators for filtering.