import os
from flask import Flask

app = Flask(__name__)

@app.route('/bybis')
def hello():
	return 'it werks'