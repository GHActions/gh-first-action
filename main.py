from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI()

# Constants
ITEM_NOT_FOUND = "Item not found"


# Pydantic model
class Item(BaseModel):
    id: int
    name: str
    price: float
    description: str | None = None


# In‑memory "database"
items_db: List[Item] = []


# Home route
@app.get("/")
def home():
    return {"message": "Welcome to FastAPI!"}


# GET all items
@app.get("/items", response_model=List[Item])
def get_items():
    return items_db


# GET single item by ID
@app.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int):
    for item in items_db:
        if item.id == item_id:
            return item
    raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)


# POST create new item
@app.post("/items", response_model=Item)
def create_item(item: Item):
    # Basic ID uniqueness check
    for existing in items_db:
        if existing.id == item.id:
            raise HTTPException(
                status_code=400,
                detail="Item ID already exists"
            )
    items_db.append(item)
    return item


# PUT update item
@app.put("/items/{item_id}", response_model=Item)
def update_item(item_id: int, updated: Item):
    for index, existing in enumerate(items_db):
        if existing.id == item_id:
            items_db[index] = updated
            return updated
    raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)


# DELETE item
@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    for index, existing in enumerate(items_db):
        if existing.id == item_id:
            del items_db[index]
            return {"message": "Item deleted"}
    raise HTTPException(status_code=404, detail=ITEM_NOT_FOUND)
