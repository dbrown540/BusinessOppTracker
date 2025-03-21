import requests
import json
import csv
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re

#credentials
token_url = "https://services.govwin.com/neo-ws/oauth/token"
client_id = "COM0CUIB4TNK7PCMS7SLEGCKA5EA1PP146665UD2BSCS6"
client_secret = "RV8883J63V9H53N5FFCFIRJVJ839R9UU60D144616E1PK"
username = "webservices@religroupinc.com"
password = "8AV8opl2w6tA"

# Rate limiting constants
RATE_LIMIT_DELAY = 1  # seconds between API calls
MAX_RETRIES = 3

# Define the department/agency/office hierarchy
GOV_ENTITY_HIERARCHY = {
    "Departments": [
        {
            "HEALTH AND HUMAN SERVICES": {
                "id": 25212,
                "agencies": [
                    {
                        "ADMINISTRATION FOR CHILDREN AND FAMILIES": {
                            "id": 25213,
                            "offices": [
                                {
                                    "ADMINISTRATION ON CHILDREN, YOUTH AND FAMILIES": {
                                        "id": 148426
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
    ]
}

def format_response_date(date_value):
    """Format response date according to API specifications"""
    if not date_value:
        return 'N/A'
    
    # Handle relative date formats
    if isinstance(date_value, str):
        if date_value.upper() in ['24H', '1W', '30D', '3M', '6M', '1Y', '2Y', '5Y']:
            return date_value.upper()
        # Try to parse absolute date
        try:
            # Try different date formats
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%m/%d/%Y']:
                try:
                    date_obj = datetime.strptime(date_value, fmt)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            return date_value  # Return original if no format matches
        except Exception:
            return date_value
    
    # Handle dictionary format (from API response)
    if isinstance(date_value, dict):
        value = date_value.get('value')
        if value:
            return format_response_date(value)
        return 'N/A'
    
    return 'N/A'

def strip_html_tags(text):
    """Remove HTML tags from text and clean up whitespace"""
    if not text:
        return 'N/A'
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Replace HTML entities
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def handle_rate_limit(response):
    """Handle rate limiting by checking response headers and waiting if necessary"""
    if response.status_code == 429:  # Too Many Requests
        retry_after = int(response.headers.get('Retry-After', 60))
        print(f"Rate limit reached. Waiting {retry_after} seconds...")
        time.sleep(retry_after)
        return True
    return False

def make_api_request(url, headers, params=None, method='GET'):
    """Make an API request with rate limiting and retries"""
    for attempt in range(MAX_RETRIES):
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params)
            else:
                response = requests.post(url, headers=headers, data=params)
            
            if handle_rate_limit(response):
                continue
                
            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                raise
            print(f"Request failed, retrying... ({attempt + 1}/{MAX_RETRIES})")
            time.sleep(RATE_LIMIT_DELAY)

    return None

# OAuth2 token function
def get_oauth_token():
    payload = {
        'grant_type': 'password',
        'client_id': client_id,
        'client_secret': client_secret,
        'username': username,
        'password': password,
        'scope': 'read'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    try:
        print("\nGetting OAuth token...")
        response = make_api_request(token_url, headers, payload, method='POST')
        if response and response.status_code == 200:
            token_data = response.json()
            print("Successfully obtained token")
            return token_data['access_token']
        else:
            raise Exception(f"Failed to obtain token: {response.status_code if response else 'No response'}")
    except Exception as e:
        raise Exception(f"Error getting token: {str(e)}")

# Fetch contract vehicles
def get_contract_vehicles(token, opp_id):
    formatted_id = f"OPP{opp_id}"
    url = f"https://services.govwin.com/neo-ws/opportunities/{formatted_id}/contractVehicles"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    all_contract_vehicles = []
    offset = 0
    max_per_page = 100  # Maximum allowed by API

    while True:
        params = {
            'offset': offset,
            'max': max_per_page,
            'sort': 'title',  # Can be 'title' or 'type'
            'order': 'asc'    # Can be 'asc' or 'desc'
        }

        try:
            print(f"\nFetching contract vehicles for {formatted_id} (offset: {offset})")
            response = make_api_request(url, headers, params)
            if response and response.status_code == 200:
                data = response.json()
                print(f"Contract vehicles response: {data}")

                # Extract contract vehicles from the response
                contract_vehicles = data.get('contractVehicles', [])
                total_count = data.get('meta', {}).get('paging', {}).get('totalCount', 0)

                print(f"Found {len(contract_vehicles)} contract vehicles in this batch")
                print(f"Total available: {total_count}")

                # Add contract vehicles to the list
                all_contract_vehicles.extend([cv.get('title', 'N/A') for cv in contract_vehicles])

                # Break if we've got all vehicles or no more results
                if offset + max_per_page >= total_count or len(contract_vehicles) == 0:
                    break

                offset += max_per_page
                time.sleep(RATE_LIMIT_DELAY)  # Respect rate limiting between pages
            else:
                print(f"Failed to get contract vehicles: {response.status_code if response else 'No response'}")
                break
        except Exception as e:
            print(f"Error getting contract vehicles: {str(e)}")
            break

    return all_contract_vehicles

# Fetch full opportunity details (includes status)
def get_opportunity_details(token, opp_id):
    formatted_id = f"OPP{opp_id}"
    url = f"https://services.govwin.com/neo-ws/opportunities/{formatted_id}"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    try:
        print(f"\nFetching opportunity details for {formatted_id}")
        response = make_api_request(url, headers)
        if response and response.status_code == 200:
            data = response.json()
            print(f"Opportunity details response: {data}")
            return data
        else:
            print(f"Failed to get opportunity details: {response.status_code if response else 'No response'}")
    except Exception as e:
        print(f"Error getting opportunity details: {str(e)}")
    return {}

def get_gov_entity_ids(opp):
    """Extract government entity IDs from an opportunity and check if it matches any ID in our hierarchy"""
    gov_entity = opp.get('govEntity', {})
    if not gov_entity:
        return None, None, None
    
    # Get the entity ID
    entity_id = gov_entity.get('id')
    if not entity_id:
        return None, None, None

    # Get all IDs from our hierarchy
    target_ids = []
    
    # Add department IDs
    for dept in GOV_ENTITY_HIERARCHY.get('Departments', []):
        for dept_data in dept.values():
            target_ids.append(dept_data['id'])
            
            # Add agency IDs
            for agency in dept_data.get('agencies', []):
                for agency_data in agency.values():
                    target_ids.append(agency_data['id'])
                    
                    # Add office IDs
                    for office in agency_data.get('offices', []):
                        for office_data in office.values():
                            target_ids.append(office_data['id'])
    
    # If the entity ID matches any ID in our hierarchy, return it as department ID
    # (since we don't care about the exact level anymore)
    if entity_id in target_ids:
        return entity_id, None, None
    
    return None, None, None

def load_whitelist(file_path):
    """Load the whitelist of govEntity IDs from a JSON file"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        # Extract all IDs from the hierarchy
        target_ids = []
        
        # Add department IDs
        for dept in data.get('Departments', []):
            for dept_data in dept.values():
                target_ids.append(dept_data['id'])
                
                # Add agency IDs
                for agency in dept_data.get('agencies', []):
                    for agency_data in agency.values():
                        target_ids.append(agency_data['id'])
                        
                        # Add office IDs
                        for office in agency_data.get('offices', []):
                            for office_data in office.values():
                                target_ids.append(office_data['id'])
        
        return target_ids
    except Exception as e:
        print(f"Error loading whitelist: {str(e)}")
        return []

def extract_response_date_from_procurement(procurement_text):
    """Extract response date from procurement text using regex"""
    if not procurement_text:
        return None
        
    # Remove HTML tags first
    text = strip_html_tags(procurement_text)
    
    # Common date patterns in the text
    patterns = [
        r"Responses are due no later than ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Response due date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Due date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Due: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Responses due: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Responses must be submitted by ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Submission deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Deadline for submissions: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Responses due by ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Response deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Proposals due by ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Proposal deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Bids due by ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Bid deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Closing date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Closing deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final submission date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final submission deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final response date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final response deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final proposal date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final proposal deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final bid date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final bid deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final closing date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final closing deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Final deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Submission date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Submission deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Response date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Response deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Proposal date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Proposal deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Bid date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Bid deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Closing date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Closing deadline: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Date: ([A-Za-z]+ \d{1,2}, \d{4})",
        r"Deadline: ([A-Za-z]+ \d{1,2}, \d{4})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            try:
                # Parse the date string
                date_obj = datetime.strptime(date_str, '%B %d, %Y')
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    return None

def get_filtered_opportunities(whitelist_file):
    """Fetch opportunities and filter by govEntity ID"""
    # Get OAuth token first
    token = get_oauth_token()
    if not token:
        print("Failed to obtain OAuth token")
        return []

    url = "https://services.govwin.com/neo-ws/opportunities"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    # Calculate yesterday's date for 1-day filter
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
    current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    # Load whitelist of govEntity IDs
    whitelisted_ids = load_whitelist(whitelist_file)
    print(f"\nLoaded {len(whitelisted_ids)} whitelisted govEntity IDs")
    print(f"Searching for opportunities from {yesterday} to {current_time}")

    # Define valid statuses
    valid_statuses = ["Forecast Pre-RFP", "Pre-RFP", "Post-RFP", "Source Selection"]
    invalid_statuses = ["Deleted", "Cancelled", "Awarded", "Closed"]

    all_opportunities = []
    max_per_page = 100
    max_total = 400
    offset = 0

    while True:
        params = {
            'max': max_per_page,
            'offset': offset,
            'oppType': 'OPP',
            'sort': 'relevancy',
            'order': 'desc',
            'oppSelectionDateFrom': yesterday,
            'oppSelectionDateTo': current_time
        }

        try:
            response = make_api_request(url, headers, params)
            if not response or response.status_code != 200:
                print(f"Failed to retrieve opportunities: {response.status_code if response else 'No response'}")
                break

            data = response.json()
            opportunities = data.get('opportunities', [])
            total_count = data.get('totalCount', 0)

            # Process each opportunity in this batch
            for opp in opportunities:
                gov_entity = opp.get('govEntity', {})
                gov_entity_id = gov_entity.get('id')
                status = opp.get('status', 'N/A')
                
                print("\n" + "="*80)
                print(f"Opportunity:")
                print(f"ID: {opp.get('iqOppId', 'N/A')}")
                print(f"Title: {opp.get('title', 'N/A')}")
                print(f"Status: {status}")
                print(f"GovEntity ID: {gov_entity_id}")
                print(f"GovEntity Title: {gov_entity.get('title', 'N/A')}")
                print("\nFiltering Results:")
                print(f"Status: {'✓' if status in valid_statuses else '✗'}")
                print(f"GovEntity ID Match: {'✓' if gov_entity_id in whitelisted_ids else '✗'}")
                
                # Only add opportunities that match both criteria
                if gov_entity_id in whitelisted_ids and status in valid_statuses:
                    all_opportunities.append(opp)
                    print("Overall Match: ✓")
                else:
                    print("Overall Match: ✗")

            # Break conditions
            if (len(all_opportunities) >= max_total or
                offset + max_per_page >= total_count or
                len(opportunities) == 0):
                break

            offset += max_per_page
            time.sleep(RATE_LIMIT_DELAY)  # Respect rate limiting between pages

        except Exception as e:
            print(f"Error processing opportunities: {str(e)}")
            break

    print(f"\nTotal matching opportunities found: {len(all_opportunities)}")
    return all_opportunities

def save_to_csv(opportunities, filename="opportunities.csv"):
    """Save filtered opportunities to a CSV file"""
    fieldnames = [
        "Opportunity Number",
        "Opportunity Name",
        "Agency",
        "Type of Response",
        "Response Date",
        "Description of Work",
        "Lead Sector",
        "Priority",
        "Primary NAICS/SIN",
        "Set-Aside",
        "LOE",
        "Status",
        "Government Entity ID",
        "Government Entity Title",
        "Procurement"
    ]

    print(f"\nSaving {len(opportunities)} opportunities to {filename}...")

    with open(filename, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for opp in opportunities:
            gov_entity = opp.get('govEntity', {})
            description = strip_html_tags(opp.get('description', 'N/A'))
            
            # Get procurement text and strip HTML tags
            procurement_text = strip_html_tags(opp.get('procurement', ''))
            
            # Try to get response date from procurement text first
            response_date = extract_response_date_from_procurement(procurement_text)
            
            # If no date found in procurement, try the API fields
            if not response_date:
                for field in ['responseDate', 'responseDateTo', 'responseDateFrom']:
                    date_value = opp.get(field)
                    if date_value:
                        if isinstance(date_value, dict):
                            date_value = date_value.get('value')
                        if date_value:
                            response_date = format_response_date(date_value)
                            break
            
            if not response_date:
                response_date = 'N/A'
            
            writer.writerow({
                "Opportunity Number": opp.get('solicitationNumber', 'N/A'),
                "Opportunity Name": opp.get('title', 'N/A'),
                "Agency": gov_entity.get('title', 'N/A'),
                "Type of Response": opp.get('typeOfAward', 'N/A'),
                "Response Date": response_date,
                "Description of Work": description,
                "Lead Sector": opp.get('primaryRequirement', 'N/A'),
                "Priority": opp.get('priority', 'N/A'),
                "Primary NAICS/SIN": opp.get('primaryNAICS', {}).get('title', 'N/A'),
                "Set-Aside": ", ".join([ct.get('title', 'N/A') for ct in opp.get('competitionTypes', [])]) if opp.get('competitionTypes') else 'N/A',
                "LOE": opp.get('duration', 'N/A'),
                "Status": opp.get('status', 'N/A'),
                "Government Entity ID": gov_entity.get('id', 'N/A'),
                "Government Entity Title": gov_entity.get('title', 'N/A'),
                "Procurement": procurement_text
            })

    print("Save completed.")

# Main function
def main():
    whitelist_file = "gov_entities.json"  # Path to your JSON file with the hierarchy
    
    try:
        opportunities = get_filtered_opportunities(whitelist_file)
        if opportunities:
            save_to_csv(opportunities)
            print(f"\nSuccessfully saved {len(opportunities)} opportunities to opportunities.csv")
        else:
            print("\nNo matching opportunities found to save")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
