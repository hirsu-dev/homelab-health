import argparse
import uvicorn
from .server import create_app

parser = argparse.ArgumentParser(
    description="Lantern. Synthetic by default; only --config enables explicit checks."
)
parser.add_argument(
    "--config",
    help="Explicit service configuration. Enables only listed HTTP/TCP checks.",
)
parser.add_argument("--database", default="data/lantern.sqlite")
parser.add_argument("--port", type=int, default=8143)
args = parser.parse_args()
uvicorn.run(create_app(args.config, args.database), host="127.0.0.1", port=args.port)
