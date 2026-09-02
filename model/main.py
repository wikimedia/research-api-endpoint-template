from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlitedict import SqliteDict

app = FastAPI()
# Enable CORS for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
)

#SUGGESTIONS_DB = SqliteDict("/etc/api-endpoint/suggestions.db")
SUGGESTIONS_DB = SqliteDict("./suggestions.db")
print(f"There are {len(SUGGESTIONS_DB)} pages in the database.")

@app.post('/v1/models/editing-suggestions:predict')
def get_source_verification_suggestions(wiki_id: str, page_id: int):
    """Get similar articles -- optionally filtered by categories, Wikidata, and/or quality."""    
    return SUGGESTIONS_DB.get(f"{wiki_id}-{page_id}", [])


if __name__ == "__main__":
    app.run()