import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def cleanup(chat_id):
    base_dir = os.path.join("user", "chats", str(chat_id))
    
    # Directories to check for obsolete files
    dirs_to_check = {
        "l2": os.path.join(base_dir, "l2"),
        "l3": os.path.join(base_dir, "l3"),
    }
    
    print(f"Scanning for obsolete files in chat {chat_id}...")
    
    for level, path in dirs_to_check.items():
        if not os.path.exists(path):
            continue
            
        print(f"Checking {level} ({path})...")
        for filename in os.listdir(path):
            if filename.endswith(".obsolete"):
                continue
                
            full_path = os.path.join(path, filename)
            if os.path.isfile(full_path):
                new_path = full_path + ".obsolete"
                print(f"Marking as obsolete: {filename}")
                os.rename(full_path, new_path)

    # Also check for old python scripts in memory_core if any (user mentioned "old Python scripts")
    # Assuming this refers to scripts that might have been replaced or are no longer needed.
    # Since I don't know exactly which scripts are "old", I will stick to the L2/L3 files as explicitly mentioned in the "Cleanup" section:
    # "List all Level 2 and Level 3 files (and old Python scripts) as "Obsolete""
    
    # If there were specific scripts mentioned, I would rename them too.
    # For now, I'll just handle L2 and L3 folders content.

if __name__ == "__main__":
    # You might need to adjust chat ID or iterate over all chats
    chat_id = "8332159226" 
    cleanup(chat_id)
