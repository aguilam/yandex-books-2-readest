import hashlib
from pathlib import Path
import json
import requests
from config import (
    books_ext,
    cover_ext,
    processing_directory,
    DEFAULT_PER_PAGE,
    API_BASE_URL,
)
import time


def md5_file(path, chunk_size=8192):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def get_book_data(elem: Path):
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
                                f"epubcfi({lib_card['cfi']})" if lib_card["cfi"] else {}
                            )
                        }
                    )
                if len(json_book["publishers"]) > 0:
                    book["publisher"] = json_book["publishers"][0]["name"]
                book["language"] = json_book["language"]
                book["title"] = json_book["title"]
                book["authors"] = json_book["authors"]
                book["description"] = json_book["annotation"]
        if book["path"]:
            book["hash"] = md5_file(book["path"])
            return book


def get_user_key_data(
    user_id: str | int, key: str, sleep=0.3, per_page=DEFAULT_PER_PAGE, cache=True
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
