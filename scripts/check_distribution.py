from pathlib import Path, PurePosixPath
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheels = list((ROOT / "dist").glob("*.whl"))
    sources = list((ROOT / "dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise RuntimeError("expected exactly one wheel and one source distribution")
    with zipfile.ZipFile(wheels[0]) as archive:
        for name in archive.namelist():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not (
                path.parts[0] == "regdelta" or path.parts[0].endswith(".dist-info")
            ):
                raise RuntimeError("unexpected wheel member")
    allowed = {"pyproject.toml", "README.md", "CONTRIBUTING.md", "SECURITY.md", "PKG-INFO", ".gitignore"}
    with tarfile.open(sources[0]) as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise RuntimeError("unsafe source distribution member")
            relative = path.parts[1:]
            if member.isfile() and not (
                relative[:2] == ("src", "regdelta")
                or len(relative) == 1 and relative[0] in allowed
            ):
                raise RuntimeError("unexpected source distribution member")
    print("Distribution inventories passed; evidence and local configuration excluded.")


if __name__ == "__main__":
    main()
