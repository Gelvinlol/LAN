import os

from waitress import serve

from app import app


def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    if os.environ.get("FLASK_DEBUG", "false").lower() == "true":
        app.run(host=host, port=port, debug=True)
    else:
        serve(app, host=host, port=port, threads=int(os.environ.get("WEB_THREADS", "4")))

if __name__ == '__main__':
    main()
