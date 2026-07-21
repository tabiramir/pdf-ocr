import requests
import glob
import os

#  CHANGE THIS TO YOUR ACTUAL FOLDER PATH
PDF_FOLDER = r"C:\Users\TabraJavaid\Downloads\files" 

url = "http://127.0.0.1:8000/process-batch/"

# Automatically find ALL .pdf files in the folder (case-insensitive)
file_paths = glob.glob(os.path.join(PDF_FOLDER, "*.pdf")) + \
             glob.glob(os.path.join(PDF_FOLDER, "*.PDF"))

if not file_paths:
    print(f"❌ No PDF files found in: {PDF_FOLDER}")
    exit(1)

print(f"🔍 Found {len(file_paths)} PDF(s) in folder.")

files_to_send = []
for path in file_paths:
    try:
        filename = os.path.basename(path)
        files_to_send.append(("files", (filename, open(path, "rb"), "application/pdf")))
        print(f"  ✅ Loaded: {filename}")
    except Exception as e:
        print(f"  ⚠️  Skipped '{filename}': {e}")

if not files_to_send:
    print("❌ No valid files could be loaded.")
else:
    print(f"\n🚀 Sending {len(files_to_send)} file(s) to server...")
    try:
        response = requests.post(url, files=files_to_send)
        print(f"✅ Status Code: {response.status_code}")
        
        # Pretty print the JSON response
        import json
        print(json.dumps(response.json(), indent=2))
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is your FastAPI server running? Run 'python run.py' first.")