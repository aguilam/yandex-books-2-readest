from pathlib import Path

input_directory = Path("input")
input_directory.mkdir(exist_ok=True)
processing_directory = Path("processing")
processing_directory.mkdir(exist_ok=True)
output_directory = Path("output")
output_directory.mkdir(exist_ok=True)

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
