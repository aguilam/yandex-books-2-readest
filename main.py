from pathlib import Path
import json
from nanoid import generate
import hashlib
from yandex_book import User
import argparse

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

input_directory = Path("input")
processing_directory = Path("processing")
output_directory = Path("output")
books_ext = (".epub", ".pdf", ".mobi", ".fb2")
cover_ext = (".png", ".jpg", ".jpeg")


def md5_file(path, chunk_size=8192):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument("uuid")
    args = argparser.parse_args()
    USER_ID = args.uuid
    user_books_uuid = []
    # for book in User.list_books(USER_ID):
    #    user_books_uuid.append(book.uuid)
    books = []
    # print(user_books_uuid)
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
                            {"location": lib_card["cfi"] if lib_card["cfi"] else {}}
                        )
                    if len(json_book["publishers"]) > 0:
                        book["publisher"] = json_book["publishers"][0]["name"]
                    book["language"] = json_book["language"]
                    book["title"] = json_book["title"]
                    book["authors"] = json_book["authors"]
            book["hash"] = md5_file(book["path"])
            books.append(book)

    quotes = User.list_quotes(USER_ID)
    imported_quotes = {}
    for quote in quotes:
        state = quote.state
        if state != "exists":
            continue
        uuid = generate(size=7)
        cfi = quote.cfi
        color = colors[quote.color]
        content = quote.content
        created_at = quote.created_at
        comment = quote.comment
        progress = quote.progress
        content_id = quote.item_uuid
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
            # "progress": progress,
        }
        if content_id not in imported_quotes:
            imported_quotes[content_id] = {"booknotes": []}
        imported_quotes[content_id]["booknotes"].append(processed_quote)

    for book in books:
        if book["uuid"] in imported_quotes:
            book["booknotes"] = imported_quotes[book["uuid"]]["booknotes"]


if __name__ == "__main__":
    main()
