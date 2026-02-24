from pathlib import Path
import json
from nanoid import generate
import hashlib
import argparse
import requests
import time
import shutil

colors = {
    0: "yellow",
    1: "red",
    2: "blue",
    3: "green",
    4: "violet",
}

baseBookConfig = {
    "viewSettings": {
        "ttsHighlightOptions": {"style": "highlight", "color": "#808080"},
        "noteExportConfig": {
            "includeTitle": True,
            "includeAuthor": True,
            "includeDate": True,
            "includeChapterTitles": True,
            "includeQuotes": True,
            "includeNotes": True,
            "includeTimestamp": False,
            "includeChapterSeparator": False,
            "noteSeparator": "\n\n",
            "useCustomTemplate": False,
            "customTemplate": "",
            "exportAsPlainText": False,
        },
    },
    "searchConfig": {},
}
API_BASE_URL = "https://api.bookmate.ru/api/v5"
DEFAULT_PER_PAGE = 20

books_ext = (".epub", ".pdf", ".mobi", ".fb2")
cover_ext = (".png", ".jpg", ".jpeg")

input_directory = Path("input")
input_directory.mkdir(exist_ok=True)
processing_directory = Path("processing")
processing_directory.mkdir(exist_ok=True)
output_directory = Path("output")
output_directory.mkdir(exist_ok=True)


def md5_file(path, chunk_size=8192):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def get_user_key_data(
    user_id: str | int, key: str, sleep=0.5, per_page=DEFAULT_PER_PAGE, cache=True
) -> list:
    processing_key = processing_directory / f"{key}.json"

    if cache and processing_key.exists():
        with open(processing_key, "r", encoding="utf-8") as f:
            return json.load(f)

    page = 1
    all_books = []

    with requests.Session() as s:
        while True:
            time.sleep(sleep)

            params = {"page": page}
            if per_page != DEFAULT_PER_PAGE:
                params["per_page"] = per_page

            resp = s.get(
                f"{API_BASE_URL}/users/{user_id}/{key}",
                params=params,
                timeout=10,
            )
            resp.raise_for_status()

            data = resp.json()
            books = data.get(key, [])

            if not books:
                break

            all_books.extend(books)
            page += 1

    with open(processing_key, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False)

    return all_books


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("uuid")
    args = argparser.parse_args()
    USER_ID = args.uuid
    user_books_uuid = []
    for book in get_user_key_data(USER_ID, "books"):
        user_books_uuid.append(book["uuid"])
    books = []
    for elem in input_directory.glob("*"):
        if elem.is_dir():
            book = {"path": None, "cover": None}
            for file in elem.iterdir():
                suffix = file.suffix
                if suffix in books_ext and book["path"] is None:
                    book["path"] = file
                elif suffix in cover_ext and book["cover"] is None:
                    book["cover"] = file
                elif suffix == ".json":
                    json_book = json.loads(file.read_text(encoding="utf-8"))["book"]
                    book["uuid"] = json_book["uuid"]
                    if json_book["library_card"]:
                        lib_card = json_book["library_card"]
                        book.update(
                            {"readingStatus": lib_card["state"]}
                            if lib_card["state"] == "finished"
                            else {}
                        )
                        book.update(
                            {
                                "location": (
                                    f"epubcfi({lib_card['cfi']})"
                                    if lib_card["cfi"]
                                    else {}
                                )
                            }
                        )
                    if len(json_book["publishers"]) > 0:
                        book["publisher"] = json_book["publishers"][0]["name"]
                    book["language"] = json_book["language"]
                    book["title"] = json_book["title"]
                    book["authors"] = json_book["authors"]
                    book["description"] = json_book["annotation"]
            book["hash"] = md5_file(book["path"])
            books.append(book)

    quotes = get_user_key_data(USER_ID, "quotes", 0.7, 50)
    imported_quotes = {}
    for quote in quotes:
        state = quote["state"]
        if state != "exists":
            continue
        uuid = generate(size=7)
        cfi = quote["cfi"]
        color = colors[quote["color"]]
        content = quote["content"]
        created_at = quote["created_at"] * 1000
        comment = quote["comment"]
        content_id = quote["book"]["uuid"]
        style = "underline" if comment is not None else "highlight"
        processed_quote = {
            "id": uuid,
            "type": "annotation",
            "cfi": f"epubcfi({cfi})",
            "style": style,
            "color": color,
            "text": content,
            "note": comment,
            "createdAt": created_at,
            "updatedAt": created_at,
        }
        if content_id not in imported_quotes:
            imported_quotes[content_id] = {"booknotes": []}
        imported_quotes[content_id]["booknotes"].append(processed_quote)

    for book in books:
        if book["uuid"] in imported_quotes:
            book["booknotes"] = imported_quotes[book["uuid"]]["booknotes"]

    new_library_books = []

    for book in books:
        current_time = int(time.time() * 1000)
        book_card = {
            "hash": book["hash"],
            "format": book["path"].suffix.upper().replace(".", ""),
            "title": book["title"],
            "sourceTitle": book["title"],
            "primaryLanguage": book["language"],
            "author": book["authors"],
            "metadata": {
                "title": book["title"],
                "language": book["language"],
                "description": book["description"],
                "author": book["authors"],
            },
            "createdAt": current_time,
            "uploadedAt": None,
            "deletedAt": None,
            "downloadedAt": current_time,
            "updatedAt": current_time,
        }

        if book.get("readingStatus"):
            book_card["readingStatus"] = book["readingStatus"]
        if book.get("publisher"):
            book_card["metadata"]["publisher"] = book["publisher"]

        new_library_books.append(book_card)

        book_config = {
            "updatedAt": current_time,
            **baseBookConfig,
            "booknotes": book.get("booknotes", []),
        }
        if book.get("location"):
            book_config["location"] = book["location"]

        book_dir = Path(output_directory / book["hash"])
        book_dir.mkdir(exist_ok=True)
        shutil.copy2(book["path"], book_dir)

        cover_src = Path(book["cover"])
        cover_dst = book_dir / f"cover.png"
        shutil.copy2(cover_src, cover_dst)

        with open(Path(book_dir / "config.json"), "w", encoding="utf-8") as f:
            json.dump(book_config, f, ensure_ascii=False)

    library_config = Path(output_directory / "library.json")
    json_books = []
    if library_config.exists():
        with open(library_config, "r", encoding="utf-8") as f:
            json_books = json.load(f)
    json_books.extend(new_library_books)
    with open(library_config, "w", encoding="utf-8") as f:
        json.dump(json_books, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
