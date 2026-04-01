import json
import os

def analyze_contacts(file_path):
    """
    Reads the content embedded JSON file and extracts basic statistics,
    such as the total number of contacts and all unique tags used.
    """
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
            total_contacts = len(data)
            unique_tags = set()
            
            # Extract tags from all contacts
            for contact in data:
                tags = contact.get('tags', [])
                unique_tags.update(tags)
                
            print(f"--- Data Analysis Report ---")
            print(f"Total Contacts Processed: {total_contacts}")
            print(f"Total Unique Tags Found: {len(unique_tags)}")
            print("-" * 28)
            print("Tags:")
            for tag in sorted(unique_tags):
                print(f" - {tag}")
            print("-" * 28)
            print("End of Report")

    except json.JSONDecodeError:
        print("Error: The file is not a valid JSON.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    # We assume 'content_embabed.json' is in the same directory as this script.
    current_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_dir, 'content_embabed.json')
    
    analyze_contacts(json_path)
