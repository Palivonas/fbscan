import os
from flask import Flask, request, jsonify
import json

app = Flask(__name__)

@app.route('/')
def index():
	return 'go to /fetch'

@app.route('/fetch', methods = ['GET', 'POST'])
def fetch():
	return jsonify(request.args)

if __name__ == '__main__':
	app.run(debug = True)