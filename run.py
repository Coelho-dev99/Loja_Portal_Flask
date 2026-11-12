from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True apenas em desenvolvimento
    app.run(debug=True)
