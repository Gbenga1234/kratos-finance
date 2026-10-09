import code

from app.config import get_settings
from app.database import Base, SessionLocal
from app.models import Transfer


def main() -> None:
    namespace = {
        "Base": Base,
        "SessionLocal": SessionLocal,
        "Transfer": Transfer,
        "settings": get_settings(),
    }
    code.interact(
        banner="Kratos Finance shell. Available: Base, SessionLocal, Transfer, settings",
        local=namespace,
    )


if __name__ == "__main__":
    main()
