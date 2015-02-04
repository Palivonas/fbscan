import os
from flask import Flask, request, jsonify, render_template
import fb

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('debug.html')

@app.route('/fetch', methods = ['GET', 'POST'])
def fetch():
	return fb.run(request.args['group_id'], singlify(request.args))

def singlify(args):
	splitup = dict(args)
	for k in splitup:
		if isinstance(splitup[k], list):
			if len(splitup[k]) == 1 and isinstance(splitup[k][0], str):
				splitup[k] = splitup[k][0]
	return splitup

if __name__ == '__main__':
	app.run(debug = True)