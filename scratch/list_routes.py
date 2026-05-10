from src.api.app import app

for route in app.routes:
    print(f"Path: {route.path} | Name: {route.name} | Methods: {route.methods}")
