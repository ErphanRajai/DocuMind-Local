import webview
import time
import urllib.request

STREAMLIT_URL = "http://127.0.0.1:8501"

def wait_for_server(url, timeout=30):
    """صبر می‌کند تا سرور استریم‌لیت کاملاً بالا بیاید تا صفحه سفید یا ارور اتصال نشان ندهد"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url) as response:
                if response.getcode() == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False

if __name__ == "__main__":
    print("⏳ Waiting for DocuMind UI to become ready...")
    
    if wait_for_server(STREAMLIT_URL):
        print("🚀 Launching DocuMind Desktop Application...")
        webview.create_window(
            title="DocuMind Local AI Workspace",
            url=STREAMLIT_URL,
            width=1300,
            height=850,
            min_size=(900, 600),
            text_select=True,
            zoomable=True
        )
        webview.start()
    else:
        print("❌ Error: Streamlit server did not respond in time.")