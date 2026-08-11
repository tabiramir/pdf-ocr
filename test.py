import requests
import os
import glob

# 1. Define the folder containing your PDFs (Update this path!)
pdf_folder = "/Users/tabra.javaid/Documents/files" 

# 2. Get all PDF files
pdf_files = glob.glob(os.path.join(pdf_folder, "*.pdf"))

if not pdf_files:
    print("❌ No PDFs found in the specified folder!")
    exit()

print(f"🔍 Found {len(pdf_files)} PDF(s) in folder.")

# 3. Prepare the files for multipart upload
files_to_upload = []
for pdf_path in pdf_files:
    filename = os.path.basename(pdf_path)
    print(f"  ✅ Loaded: {filename}")
    # The field name "files" MUST match the argument name in your FastAPI endpoint
    files_to_upload.append(
        ("files", (filename, open(pdf_path, "rb"), "application/pdf"))
    )

try:
    # 4. Send the POST request to the CORRECT endpoint
    url = "http://localhost:8000/process-batch/"
    
    print(f"\n🚀 Sending {len(files_to_upload)} file(s) to {url}...")
    
    response = requests.post(url, files=files_to_upload)
    
    print(f"\n✅ Status Code: {response.status_code}")
    print(response.json())

except requests.exceptions.ConnectionError:
    print("❌ Connection Error: Is the uvicorn server running?")
except Exception as e:
    print(f"❌ Error: {e}")

finally:
    # Always close file handles to prevent memory leaks
    for _, (_, f, _) in files_to_upload:
        f.close()