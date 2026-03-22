from pathlib import Path
import json
from nanoid import generate
import hashlib
import argparse
import requests
import time
import shutil
from config import input_directory, output_directory, colors, baseBookConfig
from parser import epub_cfi_converter
import subprocess
import sys
from utils import get_book_data, get_user_key_data


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("uuid")
    argparser.add_argument("--download", action="store_true")
    argparser.add_argument("--sleep", type=float, default=0.3)
    argparser.add_argument("--no-cache", dest="use_cache", action="store_false")
    args = argparser.parse_args()
    USER_ID: str = args.uuid
    USER_ID = USER_ID if USER_ID.startswith("@") else "@" + USER_ID
    is_need_download = args.download
    sleep_time = args.sleep
    cache = args.use_cache
    user_books = get_user_key_data(USER_ID, "books", sleep_time, cache=cache)

    user_books = {book["uuid"]: {} for book in user_books}

    for elem in input_directory.glob("*"):
        book = get_book_data(elem)
        if not book:
            continue
        user_books[book["uuid"]] = book

    if is_need_download:
        try:
            for uuid, book in user_books.items():
                if not book:
                    subprocess.run(
                        [
                            sys.executable,
                            "bookmate_downloader/RUBookmatedownloader.py",
                            "book",
                            str(uuid),
                        ]
                    )
            books_path = Path("mybooks", "book")
            for elem in books_path.glob("*"):
                new_book_path = input_directory / elem.name
                shutil.move(elem, new_book_path)
                book = get_book_data(new_book_path)
                if not book:
                    continue
                user_books[book["uuid"]] = book
        except:
            pass

    books = [v for _, v in user_books.items() if v]
    quotes = get_user_key_data(USER_ID, "quotes", sleep_time, 50, cache)
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
        for booknote in book.get("booknotes", []):
            new_note = epub_cfi_converter(book["path"], booknote["cfi"])
            booknote["cfi"] = new_note
        book_config = {
            "updatedAt": current_time,
            **baseBookConfig,
            "booknotes": book.get("booknotes", []),
        }
        if book.get("location"):
            location = epub_cfi_converter(book["path"], book["location"])
            book_config["location"] = location

        book_dir = Path(output_directory / book["hash"])
        book_dir.mkdir(exist_ok=True)
        shutil.copy2(book["path"], book_dir)

        if book.get("cover") and Path(book["cover"]).exists():
            cover_src = Path(book["cover"])
            cover_dst = book_dir / "cover.png"
            shutil.copy2(cover_src, cover_dst)

        with open(Path(book_dir / "config.json"), "w", encoding="utf-8") as f:
            json.dump(book_config, f, ensure_ascii=False)

    library_config = Path(input_directory / "library.json")
    json_books = []
    if library_config.exists():
        with open(library_config, "r", encoding="utf-8") as f:
            json_books = json.load(f)
    json_books.extend(new_library_books)
    with open(Path(output_directory / "library.json"), "w", encoding="utf-8") as f:
        json.dump(json_books, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
