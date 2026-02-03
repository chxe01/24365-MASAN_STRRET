@app.get("/user-settings", response_class=HTMLResponse)
async def user_settings_page():
    try:
        with open("Frontend_code/user-settings.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>main Page HTML File Not Found</h1>", status_code=404)
