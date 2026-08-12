from __future__ import annotations

import uvicorn

URL = "http://127.0.0.1:8765"

if __name__ == "__main__":
    print()
    print("Questlog TL Farm Planner is starting at:")
    print(f"  {URL}")
    print()
    print("An existing planner tab will refresh itself automatically.")
    print("If no planner tab is open, run OPEN_APP.bat.")
    print()
    uvicorn.run("backend:app", host="127.0.0.1", port=8765, reload=False)
