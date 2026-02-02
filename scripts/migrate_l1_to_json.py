import os
import json
import time
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from memory_core.vector_manager import VectorManager

def migrate(l1_dir):
    print(f"Starting migration in {l1_dir}...")
    
    if not os.path.exists(l1_dir):
        print("L1 directory does not exist.")
        return

    files = [f for f in os.listdir(l1_dir) if f.endswith(".md")]
    
    for filename in files:
        md_path = os.path.join(l1_dir, filename)
        json_filename = filename.replace(".md", ".json")
        json_path = os.path.join(l1_dir, json_filename)
        
        if os.path.exists(json_path):
            print(f"Skipping {filename}, JSON already exists.")
            continue
            
        print(f"Converting {filename}...")
        
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Simple heuristic parsing for legacy MD files
        # Assuming format:
        # # Summary
        # ...
        # # Bullets
        # - ...
        
        diary_entry = ""
        bullets = []
        
        lines = content.split('\n')
        mode = "diary"
        
        for line in lines:
            if "bullets" in line.lower() and line.startswith("#"):
                mode = "bullets"
                continue
            
            if mode == "diary":
                if not line.startswith("#"):
                    diary_entry += line + "\n"
            elif mode == "bullets":
                if line.strip().startswith("-"):
                    bullets.append(line.strip()[1:].strip())
        
        l1_id = filename.replace(".md", "")
        
        data = {
            "id": l1_id,
            "diary_entry": diary_entry.strip(),
            "bullets": bullets,
            "rules_locked": [], # Legacy files might not have explicit rules extracted
            "timestamp": str(time.time()) # Approximate
        }
        
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        print(f"Created {json_filename}")
        
        # Mark MD as obsolete (rename)
        os.rename(md_path, md_path + ".obsolete")

    print("Migration complete. Run the main agent to trigger Integrity Sync.")

if __name__ == "__main__":
    # Assuming standard path structure
    # You might need to adjust chat ID
    chat_id = "8332159226" # From user context
    l1_path = os.path.join("user", "chats", chat_id, "l1")
    migrate(l1_path)
