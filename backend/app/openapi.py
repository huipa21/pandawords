import json

from app.main import create_app


def main() -> None:
    print(json.dumps(create_app().openapi(), indent=2))


if __name__ == "__main__":
    main()
