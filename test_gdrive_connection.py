import os
import sys
import json

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings

def test_gdrive_setup():
    print("=" * 65)
    print("🔍 GOOGLE DRIVE INTEGRATION DIAGNOSTIC & VERIFICATION TOOL")
    print("=" * 65)

    sa_file = settings.GDRIVE_SERVICE_ACCOUNT_FILE or "service_account.json"
    folder_id = settings.GDRIVE_FOLDER_ID

    print(f"\n[1] Checking Service Account Key File: '{sa_file}'")
    if not os.path.exists(sa_file):
        print(f"❌ ERROR: File '{sa_file}' NOT FOUND in {os.path.abspath('.')}")
        print("\n👉 To fix this:")
        print("1. Go to Google Cloud Console (https://console.cloud.google.com/)")
        print("2. Create a Service Account -> Keys -> Add Key -> JSON")
        print(f"3. Download the JSON file and save it as '{sa_file}' in your project root: {os.path.abspath('.')}")
        return False

    try:
        with open(sa_file, "r") as f:
            sa_data = json.load(f)
        client_email = sa_data.get("client_email")
        project_id = sa_data.get("project_id")
        print(f"✅ Key file is valid JSON.")
        print(f"   • Project ID: {project_id}")
        print(f"   • Service Account Email: {client_email}")
    except Exception as e:
        print(f"❌ ERROR reading '{sa_file}': {e}")
        return False

    print(f"\n[2] Initializing Google Drive API Client...")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload
        import io

        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = service_account.Credentials.from_service_account_file(
            sa_file, scopes=scopes
        )
        service = build("drive", "v3", credentials=credentials)
        print("✅ Google Drive API client initialized successfully.")
    except Exception as e:
        print(f"❌ Google Drive Client Authentication Failed: {e}")
        return False

    print(f"\n[3] Verifying Target Folder Access...")
    if folder_id:
        print(f"   • Configured Folder ID: {folder_id}")
        try:
            folder = service.files().get(fileId=folder_id, fields="id, name, capabilities").execute()
            can_add = folder.get("capabilities", {}).get("canAddChildren", False)
            print(f"✅ Target folder located: '{folder.get('name')}' (ID: {folder.get('id')})")
            if not can_add:
                print(f"⚠️ WARNING: Service account does NOT have write permission on this folder.")
                print(f"👉 Please share folder '{folder.get('name')}' with '{client_email}' and grant 'Editor' role.")
        except Exception as e:
            print(f"❌ Cannot access Google Drive folder ID '{folder_id}': {e}")
            print(f"\n👉 Fix:")
            print(f"1. Open Google Drive in your browser.")
            print(f"2. Right click your avatars folder -> Share -> Add '{client_email}' as 'Editor'.")
            return False
    else:
        print("ℹ️ No specific GDRIVE_FOLDER_ID configured. Files will be uploaded to Service Account root drive.")
        print(f"💡 Recommended: Create a folder named 'HRMS_Avatars' in Google Drive and share it with '{client_email}'.")

    print(f"\n[4] Performing Test Upload & CDN Preview Verification...")
    test_file_id = None
    try:
        dummy_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        file_metadata = {
            "name": "hrms_storage_diagnostic_test.png",
            "mimeType": "image/png"
        }
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaIoBaseUpload(io.BytesIO(dummy_png), mimetype="image/png", resumable=False)
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
        test_file_id = uploaded.get("id")
        print(f"✅ Test file uploaded successfully! File ID: {test_file_id}")

        # Set public reader
        service.permissions().create(
            fileId=test_file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()
        print("✅ Public reader permissions set.")

        cdn_url = f"https://lh3.googleusercontent.com/d/{test_file_id}"
        print(f"✅ Direct High-Speed CDN URL: {cdn_url}")

    except Exception as e:
        print(f"❌ Upload test failed: {e}")
        if "insufficientPermissions" in str(e) or "File not found" in str(e):
            print(f"\n👉 Make sure you shared your Google Drive folder with '{client_email}' as 'Editor'!")
        return False
    finally:
        if test_file_id:
            try:
                service.files().delete(fileId=test_file_id).execute()
                print(f"✅ Diagnostic test file cleaned up from Google Drive.")
            except Exception:
                pass

    print("\n" + "=" * 65)
    print("🎉 GOOGLE DRIVE STORAGE IS 100% READY AND FUNCTIONAL!")
    print("=" * 65)
    print("\nTo activate Google Drive across your HRMS portal:")
    print("In your .env file, ensure you have:")
    print("STORAGE_PROVIDER=gdrive")
    print(f"GDRIVE_SERVICE_ACCOUNT_FILE={sa_file}")
    if folder_id:
        print(f"GDRIVE_FOLDER_ID={folder_id}")
    return True

if __name__ == "__main__":
    test_gdrive_setup()
