from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>Merhaba! toolgundem calisiyor.</h1><p>Bu ilk test sayfasi.</p>"

if __name__ == "__main__":
    app.run(debug=True, port=5000)
