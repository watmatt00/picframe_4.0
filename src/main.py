"""
PicFrame 4.0 - Main entry point.

Usage:
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000

Or via CLI:
    picframe-api
"""

import uvicorn


def main():
    """Run the PicFrame API server."""
    uvicorn.run(
        "src.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
