import os
from flask import Flask
import sys

app = Flask(__name__)

@app.route('/')
def index():
	return str(sys.version)

@app.route('/bybis')
def bybis():
	return str(sys.version)