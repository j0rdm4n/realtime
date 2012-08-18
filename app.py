from flask import Flask, render_template
import os

app = Flask('wavesofcode')
NODE_HOST = 'http://localhost:8020' if os.environ.get('USERNAME') else 'http://doda.co:8020'

@app.route('/')
@app.route('/<string:temp>')
def home(temp=''):
    return render_template((temp or 'index')+'.html', NODE_HOST=NODE_HOST)

if __name__ == '__main__':
    app.run(debug=True)
