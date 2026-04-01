"""Open a URL in the system's default browser."""

import webbrowser


def browser_open(url: str) -> str:
    try:
        webbrowser.open(url)
        return f"Opened in browser: {url}"
    except Exception as e:
        return f"Browser open error: {str(e)}"
