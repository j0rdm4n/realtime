from flask import Flask, render_template

app = Flask('wavesofcode')

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/stats')
def stats():
    return render_template('stats.html')

@app.route('/photos')
def photos():
    return render_template('photos.html')

if __name__ == '__main__':
    app.run(debug=True)
