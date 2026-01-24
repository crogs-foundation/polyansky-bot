from pathlib import Path

ROOT_PATH = Path(__file__).parent.parent.parent.resolve()


def create_path(*args: str | Path) -> Path:
    return Path(ROOT_PATH, *args)


if __name__ == "__main__":
    print(create_path("data/images"))
